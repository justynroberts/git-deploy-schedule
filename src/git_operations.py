"""Git operations wrapper for managing repository commits."""

import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
import git
from git.exc import GitCommandError, InvalidGitRepositoryError


logger = logging.getLogger(__name__)


class GitOperations:
    """Wrapper for git operations."""

    def __init__(self, repo_path: str, branch: str = "main"):
        """Initialize git operations.

        Args:
            repo_path: Path to git repository
            branch: Branch name to work with

        Raises:
            InvalidGitRepositoryError: If path is not a git repository
        """
        self.repo_path = Path(repo_path).resolve()
        self.branch = branch

        try:
            self.repo = git.Repo(self.repo_path)
            logger.info(f"Initialized git repository at {self.repo_path}")
        except InvalidGitRepositoryError:
            logger.error(f"Not a git repository: {self.repo_path}")
            raise

    def get_current_branch(self) -> str:
        """Get current branch name.

        Returns:
            Current branch name
        """
        return self.repo.active_branch.name

    def has_changes(self) -> bool:
        """Check if repository has uncommitted changes.

        Returns:
            True if there are changes, False otherwise
        """
        # Check for both staged and unstaged changes
        return self.repo.is_dirty() or len(self.repo.untracked_files) > 0

    def get_status(self) -> str:
        """Get git status output.

        Returns:
            Git status string
        """
        return self.repo.git.status()

    def get_diff(self, staged: bool = True) -> str:
        """Get git diff.

        Args:
            staged: If True, get staged diff; otherwise get unstaged diff

        Returns:
            Git diff output
        """
        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")

            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True
            )
            return result.stdout
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return ""

    def get_changed_files(self) -> List[str]:
        """Get list of changed files.

        Returns:
            List of changed file paths
        """
        changed_files = []

        # Get modified and staged files
        changed_files.extend([item.a_path for item in self.repo.index.diff(None)])
        changed_files.extend([item.a_path for item in self.repo.index.diff('HEAD')])

        # Get untracked files
        changed_files.extend(self.repo.untracked_files)

        return list(set(changed_files))  # Remove duplicates

    def stage_all(self) -> bool:
        """Stage all changes.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.repo.git.add(A=True)
            logger.info("Staged all changes")
            return True
        except GitCommandError as e:
            logger.error(f"Failed to stage changes: {e}")
            return False

    def commit(self, message: str, author_name: str = None, author_email: str = None) -> bool:
        """Create a commit with the given message.

        Args:
            message: Commit message
            author_name: Author name (optional)
            author_email: Author email (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use subprocess to avoid GitPython pipe issues
            cmd = ["git", "commit", "-m", message]

            env = None
            if author_name and author_email:
                import os
                env = os.environ.copy()
                env["GIT_AUTHOR_NAME"] = author_name
                env["GIT_AUTHOR_EMAIL"] = author_email
                env["GIT_COMMITTER_NAME"] = author_name
                env["GIT_COMMITTER_EMAIL"] = author_email

            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                env=env
            )

            if result.returncode == 0:
                logger.info(f"Created commit: {message[:50]}...")
                # Refresh repo state
                self.repo = git.Repo(self.repo_path)
                return True
            else:
                logger.error(f"Failed to commit: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            return False

    def push(self, remote: str = "origin", branch: str = None, retry_attempts: int = 3, retry_delay: int = 30) -> bool:
        """Push commits to remote repository.

        Args:
            remote: Remote name
            branch: Branch name (uses instance branch if not provided)
            retry_attempts: Number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            True if successful, False otherwise
        """
        import time
        import os

        if branch is None:
            branch = self.branch

        def _read_token_from_db():
            try:
                import sqlite3 as _sqlite3
                _db_path = Path("database/scheduler.db")
                if _db_path.exists():
                    _conn = _sqlite3.connect(str(_db_path))
                    _row = _conn.execute(
                        "SELECT value FROM settings WHERE key = 'github_token'"
                    ).fetchone()
                    _conn.close()
                    return _row[0].strip() if _row else None
            except Exception:
                pass
            return None

        def _write_creds(token):
            # Refresh credentials file before each attempt so git credential-reject
            # (triggered on auth failure) can't permanently erase them.
            try:
                creds = Path.home() / ".git-credentials"
                creds.write_text(f"https://x-access-token:{token}@github.com\n")
                creds.chmod(0o600)
            except Exception:
                pass

        git_env = {**__import__("os").environ, "GIT_TERMINAL_PROMPT": "0"}

        for attempt in range(retry_attempts):
            try:
                token = _read_token_from_db()
                if token:
                    _write_creds(token)

                # Rebase on remote before pushing to avoid non-fast-forward rejection
                rebase = subprocess.run(
                    ["git", "pull", "--rebase", remote, branch],
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    env=git_env,
                )
                if rebase.returncode != 0:
                    logger.warning(f"Rebase failed: {rebase.stderr.strip()}")

                result = subprocess.run(
                    ["git", "push", remote, branch],
                    cwd=str(self.repo_path),
                    capture_output=True,
                    text=True,
                    env=git_env,
                )

                if result.returncode == 0:
                    logger.info(f"Pushed to {remote}/{branch}")
                    return True
                else:
                    raise Exception(result.stderr)

            except Exception as e:
                logger.warning(f"Push attempt {attempt + 1}/{retry_attempts} failed: {e}")
                if attempt < retry_attempts - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to push after {retry_attempts} attempts")
                    return False

        return False

    def get_remote_url(self, remote: str = "origin") -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", remote],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Strip embedded credentials
                import re
                url = re.sub(r'https://[^@]+@', 'https://', url)
                return url
            return None
        except Exception:
            return None

    def get_last_commit_hash(self) -> Optional[str]:
        """Get the last commit hash.

        Returns:
            Last commit hash or None
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get last commit hash: {e}")
            return None

    def get_last_commit_message(self) -> Optional[str]:
        """Get the last commit message.

        Returns:
            Last commit message or None
        """
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%s"],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.error(f"Failed to get last commit message: {e}")
            return None

    def get_commit_count(self) -> int:
        """Get total number of commits.

        Returns:
            Number of commits
        """
        try:
            return len(list(self.repo.iter_commits()))
        except Exception as e:
            logger.error(f"Failed to get commit count: {e}")
            return 0

    def pull(self, remote: str = "origin", branch: str = None) -> bool:
        """Pull latest changes from remote.

        Args:
            remote: Remote name
            branch: Branch name (uses instance branch if not provided)

        Returns:
            True if successful, False otherwise
        """
        if branch is None:
            branch = self.branch

        try:
            origin = self.repo.remote(remote)
            origin.pull(branch)
            logger.info(f"Pulled from {remote}/{branch}")
            return True
        except GitCommandError as e:
            logger.error(f"Failed to pull: {e}")
            return False
