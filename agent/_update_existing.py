import json
import subprocess
import yaml

with open("agent/nexuscrm-dsl.yaml") as f:
    dsl = yaml.safe_load(f)

mc = dsl["model_config"]

def psql(query):
    r = subprocess.run(
        ["docker", "exec", "dify-docker-db_postgres-1", "psql", "-U", "postgres", "-d", "dify", "-t", "-A", "-c", query],
        capture_output=True, text=True
    )
    return r.stdout.strip()

old_config_id = psql("SELECT id FROM app_model_configs WHERE app_id = '390bdd58-bc95-44b0-bbc0-304cb7535459' ORDER BY created_at DESC LIMIT 1;")
print(f"Old config ID: {old_config_id}")

def esc(s):
    return s.replace("'", "''")

update = f"""UPDATE app_model_configs SET
    pre_prompt = '{esc(mc["pre_prompt"])}',
    opening_statement = '{esc(mc["opening_statement"])}',
    suggested_questions = '{esc(json.dumps(mc["suggested_questions"]))}',
    model = '{esc(json.dumps(mc["model"]))}'
WHERE id = '{old_config_id}';"""

with open("agent/_update_existing.sql", "w") as f:
    f.write(update)

print("SQL written to agent/_update_existing.sql")
print(f"pre_prompt length: {len(mc['pre_prompt'])}")
