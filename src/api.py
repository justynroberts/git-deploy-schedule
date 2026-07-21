"""FastAPI HTTP server for web UI integration."""

import logging
import os
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .database import Database


logger = logging.getLogger(__name__)

app = FastAPI(title="Git Deploy Scheduler API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global scheduler instance (set from main)
scheduler_instance = None
db_instance = None


def set_scheduler(scheduler):
    """Set the scheduler instance for API access."""
    global scheduler_instance, db_instance
    scheduler_instance = scheduler
    db_instance = scheduler.db if scheduler else None
    if db_instance:
        _migrate_token_file()
        _load_saved_token()


class ControlAction(BaseModel):
    """Control action model."""
    action: str  # pause, resume, trigger


class TokenUpdate(BaseModel):
    """Token update model."""
    token: str


class OllamaConfig(BaseModel):
    """Ollama configuration model."""
    url: Optional[str] = None
    model: Optional[str] = None
    theme: Optional[str] = None
    system_prompt: Optional[str] = None
    enabled: Optional[bool] = None


_LEGACY_TOKEN_FILE = Path("database/.github_token")


@app.get("/")
async def root():
    """Serve the main UI page."""
    return FileResponse("web/frontend/index.html")


def _get_push_status(db):
    """Return push health: failed_recent = count of recent push failures, last_push_success = bool."""
    if not db:
        return {"enabled": False, "failed_recent": 0, "last_push_success": None, "healthy": True}
    try:
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT push_success FROM commits
            ORDER BY timestamp DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        if not rows:
            return {"enabled": True, "failed_recent": 0, "last_push_success": None, "healthy": True}
        failed = sum(1 for r in rows if not r["push_success"])
        last_ok = bool(rows[0]["push_success"])
        return {
            "enabled": True,
            "failed_recent": failed,
            "last_push_success": last_ok,
            "healthy": failed == 0,
        }
    except Exception:
        return {"enabled": True, "failed_recent": 0, "last_push_success": None, "healthy": True}


@app.get("/api/status")
async def get_status():
    """Get current scheduler status."""
    if not scheduler_instance:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        last_commit = db_instance.get_last_commit() if db_instance else None

        # Calculate next commit time
        next_in = None
        if hasattr(scheduler_instance, 'next_commit_time') and scheduler_instance.next_commit_time:
            next_in = int((scheduler_instance.next_commit_time - datetime.now()).total_seconds())
            next_in = max(0, next_in)

        return {
            "running": True,
            "paused": getattr(scheduler_instance, 'paused', False),
            "next_commit_in": next_in,
            "last_commit": {
                "hash": last_commit['hash'][:7] if last_commit else None,
                "message": last_commit['message'] if last_commit else None,
                "timestamp": last_commit['timestamp'] if last_commit else None,
                "files_changed": last_commit['files_changed'] if last_commit else 0,
                "success": last_commit['success'] if last_commit else False,
            } if last_commit else None,
            "ollama_available": scheduler_instance.ollama_client is not None if scheduler_instance else False,
            "current_theme": scheduler_instance.config.get('ollama.theme', '') if scheduler_instance else '',
            "repository": scheduler_instance.git_ops.repo_path if scheduler_instance and scheduler_instance.git_ops else None,
            "branch": scheduler_instance.git_ops.get_current_branch() if scheduler_instance and scheduler_instance.git_ops else None,
            "remote_url": scheduler_instance.git_ops.get_remote_url() if scheduler_instance and scheduler_instance.git_ops else None,
            "push_status": _get_push_status(db_instance),
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
async def get_history(limit: int = 50):
    """Get commit history."""
    if not db_instance:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        commits = db_instance.get_recent_commits(limit=limit)
        total = db_instance.get_commit_count()

        return {
            "commits": commits,
            "total": total
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get statistics."""
    if not db_instance:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        daily_stats = db_instance.get_daily_stats(days=7)
        commit_types = db_instance.get_commit_types()

        # Calculate commits last 24h
        commits_24h = daily_stats[0]['total_commits'] if daily_stats else 0

        # Get commits by day for chart
        commits_by_day = [stat['total_commits'] for stat in reversed(daily_stats)]

        return {
            "total_commits": db_instance.get_commit_count(),
            "success_rate": round(db_instance.get_success_rate(), 1),
            "ollama_usage_rate": round(db_instance.get_ollama_usage_rate(), 1),
            "commits_last_24h": commits_24h,
            "commits_by_day": commits_by_day,
            "commit_types": commit_types
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/control")
async def control_action(action: ControlAction):
    """Control the scheduler."""
    if not scheduler_instance:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        if action.action == "pause":
            scheduler_instance.paused = True
            logger.info("Scheduler paused via API")
            return {"status": "paused"}

        elif action.action == "resume":
            scheduler_instance.paused = False
            logger.info("Scheduler resumed via API")
            return {"status": "resumed"}

        elif action.action == "trigger":
            # Trigger immediate commit in background
            def trigger_commit():
                try:
                    scheduler_instance._perform_commit()
                except Exception as e:
                    logger.error(f"Error triggering commit: {e}")

            thread = threading.Thread(target=trigger_commit)
            thread.daemon = True
            thread.start()

            logger.info("Commit triggered via API")
            return {"status": "triggered"}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")

    except Exception as e:
        logger.error(f"Error in control action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    if not scheduler_instance:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        return {
            "config": scheduler_instance.config.config
        }
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """Get recent log entries."""
    try:
        log_file = "logs/scheduler.log"
        with open(log_file, 'r') as f:
            log_lines = f.readlines()
            recent_logs = log_lines[-lines:]
            return {"logs": recent_logs}
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _configure_git_credentials(token: str):
    """Configure git to use the token for authentication."""
    try:
        # Set credential helper
        subprocess.run(["git", "config", "--global", "credential.helper", "store"], check=True)

        # Write credentials file
        creds_file = Path.home() / ".git-credentials"
        creds_file.write_text(f"https://x-access-token:{token}@github.com\n")
        creds_file.chmod(0o600)

        logger.info("Git credentials configured successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to configure git credentials: {e}")
        return False


def _migrate_token_file():
    """One-time migration: move token from legacy file into DB."""
    if not db_instance or not _LEGACY_TOKEN_FILE.exists():
        return
    try:
        token = _LEGACY_TOKEN_FILE.read_text().strip()
        if token and not db_instance.get_setting("github_token"):
            db_instance.set_setting("github_token", token)
            logger.info("Migrated GitHub token from file to database")
        _LEGACY_TOKEN_FILE.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"Token migration failed: {e}")


def _load_saved_token():
    """Load token from DB and configure git credentials."""
    if not db_instance:
        return False
    token = db_instance.get_setting("github_token")
    if token:
        _configure_git_credentials(token)
        return True
    return False


@app.get("/api/settings")
async def get_settings():
    """Get current settings."""
    has_token = bool(db_instance and db_instance.get_setting("github_token"))

    # Test git push capability
    push_enabled = False
    if has_token:
        try:
            repo_path = str(scheduler_instance.git_ops.repo_path) if scheduler_instance and scheduler_instance.git_ops else os.environ.get("REPO_PATH", str(Path.home()))
            result = subprocess.run(
                ["git", "ls-remote", "--exit-code", "origin"],
                capture_output=True,
                timeout=10,
                cwd=repo_path
            )
            push_enabled = result.returncode == 0
        except Exception:
            pass

    branch = scheduler_instance.git_ops.get_current_branch() if scheduler_instance and scheduler_instance.git_ops else None
    remote_url = scheduler_instance.git_ops.get_remote_url() if scheduler_instance and scheduler_instance.git_ops else None

    return {
        "has_github_token": has_token,
        "push_enabled": push_enabled,
        "branch": branch,
        "remote_url": remote_url,
    }


class RepoConfig(BaseModel):
    branch: str = None
    remote_url: str = None


@app.post("/api/settings/repo")
async def set_repo_config(data: RepoConfig):
    """Update branch and/or remote URL live."""
    if not scheduler_instance or not scheduler_instance.git_ops:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    git_ops = scheduler_instance.git_ops
    repo_path = str(git_ops.repo_path)
    results = {}

    if data.branch:
        # Create local branch if it doesn't exist, then switch
        try:
            # Check if branch exists locally
            check = subprocess.run(
                ["git", "rev-parse", "--verify", data.branch],
                cwd=repo_path, capture_output=True, text=True
            )
            if check.returncode != 0:
                # Create branch from current HEAD
                subprocess.run(
                    ["git", "checkout", "-b", data.branch],
                    cwd=repo_path, capture_output=True, text=True, check=True
                )
            else:
                subprocess.run(
                    ["git", "checkout", data.branch],
                    cwd=repo_path, capture_output=True, text=True, check=True
                )
            # Update scheduler branch config
            scheduler_instance.config.config["repositories"][0]["branch"] = data.branch
            git_ops.branch = data.branch
            results["branch"] = f"switched to {data.branch}"
            logger.info(f"Branch updated to {data.branch}")
        except Exception as e:
            results["branch_error"] = str(e)

    if data.remote_url:
        try:
            url = data.remote_url.strip().rstrip("/")
            if not url.endswith(".git"):
                url += ".git"
            subprocess.run(
                ["git", "remote", "set-url", "origin", url],
                cwd=repo_path, capture_output=True, text=True, check=True
            )
            results["remote_url"] = f"set to {url}"
            logger.info(f"Remote URL updated to {url}")
        except Exception as e:
            results["remote_url_error"] = str(e)

    return {"status": "success", "results": results}


@app.post("/api/settings/token")
async def set_token(data: TokenUpdate):
    """Save GitHub token."""
    if not db_instance:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        db_instance.set_setting("github_token", data.token)
        if _configure_git_credentials(data.token):
            logger.info("GitHub token saved to database and configured")
            return {"status": "success", "message": "Token saved successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to configure git credentials")
    except Exception as e:
        logger.error(f"Error saving token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/settings/token")
async def delete_token():
    """Remove saved GitHub token."""
    try:
        if db_instance:
            db_instance.delete_setting("github_token")

        creds_file = Path.home() / ".git-credentials"
        if creds_file.exists():
            creds_file.unlink()

        logger.info("GitHub token removed")
        return {"status": "success", "message": "Token removed"}

    except Exception as e:
        logger.error(f"Error removing token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/ollama")
async def get_ollama_config():
    """Get current Ollama configuration."""
    if not scheduler_instance:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    cfg = scheduler_instance.config.get_ollama_config()
    # Overlay any DB-saved overrides
    if db_instance:
        for key in ("url", "model", "theme", "system_prompt", "enabled"):
            saved = db_instance.get_setting(f"ollama_{key}")
            if saved is not None:
                if key == "enabled":
                    cfg[key] = saved == "true"
                else:
                    cfg[key] = saved
    return cfg


@app.post("/api/settings/ollama")
async def set_ollama_config(data: OllamaConfig):
    """Save Ollama configuration and apply to running scheduler."""
    if not db_instance:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        updates = data.dict(exclude_none=True)
        for key, value in updates.items():
            db_instance.set_setting(f"ollama_{key}", str(value).lower() if isinstance(value, bool) else str(value))

        # Apply to running scheduler live
        if scheduler_instance:
            ollama_cfg = scheduler_instance.config.get_ollama_config()
            ollama_cfg.update(updates)
            if "url" in updates or "model" in updates:
                from .ollama_client import OllamaClient
                try:
                    client = OllamaClient(
                        url=ollama_cfg.get("url", "http://localhost:11434"),
                        model=ollama_cfg.get("model", "llama3.2:3b"),
                        timeout=ollama_cfg.get("timeout", 30),
                        max_tokens=ollama_cfg.get("max_tokens", 100),
                    )
                    if client.health_check():
                        scheduler_instance.ollama_client = client
                        scheduler_instance.message_generator.ollama_client = client
                        scheduler_instance.message_generator.use_ollama = True
                        logger.info(f"Ollama client updated: {ollama_cfg['url']}")
                    else:
                        logger.warning("New Ollama URL not reachable — keeping existing client")
                except Exception as e:
                    logger.error(f"Failed to reinitialise Ollama client: {e}")
            if "theme" in updates and scheduler_instance.config:
                scheduler_instance.config.config.setdefault("ollama", {})["theme"] = updates["theme"]
            if "system_prompt" in updates and scheduler_instance.config:
                scheduler_instance.config.config.setdefault("ollama", {})["system_prompt"] = updates["system_prompt"]

        logger.info(f"Ollama config updated: {list(updates.keys())}")
        return {"status": "success", "message": "Ollama config saved"}
    except Exception as e:
        logger.error(f"Error saving Ollama config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/ollama/test")
async def test_ollama():
    """Test Ollama connectivity."""
    if not scheduler_instance or not scheduler_instance.ollama_client:
        return {"status": "error", "message": "Ollama client not configured"}
    try:
        available = scheduler_instance.ollama_client.health_check()
        if available:
            models = scheduler_instance.ollama_client.get_models() or []
            return {"status": "success", "message": "Ollama reachable", "models": models}
        return {"status": "error", "message": "Ollama not reachable at configured URL"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/settings/test-push")
async def test_push():
    """Test git push capability with saved token."""
    try:
        repo_path = str(scheduler_instance.git_ops.repo_path) if scheduler_instance and scheduler_instance.git_ops else os.environ.get("REPO_PATH", str(Path.home()))

        # Test remote access
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "origin"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=repo_path
        )

        if result.returncode == 0:
            return {"status": "success", "message": "Git remote access working"}
        else:
            return {"status": "error", "message": f"Git remote access failed: {result.stderr}"}

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Connection timed out"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/settings/test-token")
async def test_token(data: TokenUpdate):
    """Test a token by checking push permissions via GitHub API."""
    import urllib.request
    import json as json_module

    try:
        repo_path = str(scheduler_instance.git_ops.repo_path) if scheduler_instance and scheduler_instance.git_ops else os.environ.get("REPO_PATH", str(Path.home()))

        # Get the remote URL
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=repo_path
        )

        if result.returncode != 0:
            return {"status": "error", "message": "Could not get remote URL"}

        remote_url = result.stdout.strip()

        # Extract owner/repo from URL
        # https://github.com/owner/repo.git -> owner/repo
        if "github.com" not in remote_url:
            return {"status": "error", "message": "Remote is not a GitHub URL"}

        # Parse owner/repo
        parts = remote_url.replace("https://github.com/", "").replace("git@github.com:", "").replace(".git", "").split("/")
        if len(parts) < 2:
            return {"status": "error", "message": "Could not parse repo from URL"}

        owner, repo = parts[0], parts[1]

        # Check token permissions via GitHub API
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        req = urllib.request.Request(api_url)
        req.add_header("Authorization", f"token {data.token}")
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "git-deploy-scheduler")

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                repo_data = json_module.loads(response.read().decode())

                # Check if we have push permission
                permissions = repo_data.get("permissions", {})
                can_push = permissions.get("push", False)

                if can_push:
                    return {"status": "success", "message": "Token valid with push access!"}
                else:
                    return {"status": "error", "message": "Token valid but no push permission"}

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"status": "error", "message": "Invalid token"}
            elif e.code == 403:
                return {"status": "error", "message": "Token lacks repo access"}
            elif e.code == 404:
                return {"status": "error", "message": "Repo not found or token lacks access"}
            else:
                return {"status": "error", "message": f"GitHub API error: {e.code}"}

    except Exception as e:
        logger.error(f"Error testing token: {e}")
        return {"status": "error", "message": str(e)}


# Mount static files
try:
    app.mount("/static", StaticFiles(directory="web/frontend"), name="static")
except Exception:
    pass  # Static files may not exist yet
