import random
import os
from pathlib import Path

DESTINATIONS = [
    ("bali", "Indonesia"), ("bangkok", "Thailand"), ("barcelona", "Spain"),
    ("dubai", "UAE"), ("london", "UK"), ("new-york", "USA"),
    ("paris", "France"), ("tokyo", "Japan"), ("sydney", "Australia"),
    ("rome", "Italy"), ("amsterdam", "Netherlands"), ("singapore", "Singapore"),
    ("lisbon", "Portugal"), ("istanbul", "Turkey"), ("miami", "USA"),
]

K8S_COMPONENTS = [
    ("api-gateway", "deployment"), ("backend", "deployment"), ("frontend", "deployment"),
    ("postgres", "statefulset"), ("redis", "deployment"), ("nginx", "deployment"),
    ("scheduler", "cronjob"), ("worker", "deployment"), ("auth-service", "deployment"),
    ("booking-service", "deployment"), ("payment-service", "deployment"),
]

SEASONS = ["Spring", "Summer", "Fall", "Winter"]
PRICES  = ["$", "$$", "$$$", "$$$$"]


def _destination_yaml(name, country):
    return f"""name: {name.replace('-', ' ').title()}
country: {country}
rating: {random.uniform(3.0, 5.0):.1f}/5
price_range: {random.choice(PRICES)}
best_season: {random.choice(SEASONS)}
flights_per_week: {random.randint(5, 40)}
avg_stay_days: {random.randint(3, 14)}
accommodations:
  hotels: {random.randint(10, 60)}
  hostels: {random.randint(5, 25)}
  resorts: {random.randint(2, 20)}
"""


def _k8s_yaml(name, kind):
    replicas = random.randint(1, 5)
    port     = random.randint(3000, 9000)
    return f"""apiVersion: apps/v1
kind: {kind.title().replace('job', 'Job').replace('set', 'Set')}
metadata:
  name: {name}
  namespace: travelduty
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: {name}
        image: travelduty/{name}:{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}
        ports:
        - containerPort: {port}
        resources:
          requests:
            memory: "{random.choice([64,128,256])}Mi"
            cpu: "{random.choice([100,250,500])}m"
"""


def generate_random_files(repo_path: str, count: int = 2) -> list:
    """Generate count random sample files in repo_path. Returns list of relative paths."""
    repo = Path(repo_path)
    generated = []

    choices = random.sample(["destination", "kubernetes"], k=min(count, 2))
    if count > 2:
        choices += random.choices(["destination", "kubernetes"], k=count - 2)

    for kind in choices:
        if kind == "destination":
            name, country = random.choice(DESTINATIONS)
            content  = _destination_yaml(name, country)
            rel_path = f"destinations/{name}.yaml"
        else:
            name, comp = random.choice(K8S_COMPONENTS)
            content  = _k8s_yaml(name, comp)
            rel_path = f"kubernetes/{name}-{comp}.yaml"

        full = repo / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        generated.append(rel_path)

    return generated
