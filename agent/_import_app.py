#!/usr/bin/env python3
"""Insert NexusCRM agent app directly into Dify PostgreSQL."""
import json
import subprocess
import uuid

APP_ID = str(uuid.uuid4())
CONFIG_ID = str(uuid.uuid4())
TENANT_ID = "ddfbb8da-86e0-4ff5-9a2b-f65f030e591a"
ACCOUNT_ID = "e7622295-ff99-45e2-8993-23e2881a24ec"

# Load the DSL
with open("agent/nexuscrm-dsl.yaml") as f:
    import yaml
    dsl = yaml.safe_load(f)

model_config = dsl["model_config"]
app_meta = dsl["app"]

# Build the SQL
# 1. Insert app
insert_app_sql = f"""
INSERT INTO apps (id, tenant_id, mode, name, description, icon_type, icon, icon_background,
    enable_site, enable_api, use_icon_as_answer_icon, created_by, updated_by)
VALUES (
    '{APP_ID}',
    '{TENANT_ID}',
    'agent-chat',
    '{app_meta["name"]}',
    '{app_meta["description"].replace("'", "''")}',
    'emoji',
    '\\U0001F4CA',
    '{app_meta["icon_background"]}',
    true, true, false,
    '{ACCOUNT_ID}', '{ACCOUNT_ID}'
);
"""

# 2. Insert model config
def sql_json(obj):
    """Convert Python object to SQL-escaped JSON string."""
    return json.dumps(obj, ensure_ascii=False).replace("'", "''")

insert_config_sql = f"""
INSERT INTO app_model_configs (id, app_id, provider, model_id, configs,
    created_at, updated_at,
    opening_statement, suggested_questions, suggested_questions_after_answer,
    more_like_this, model, user_input_form, pre_prompt, agent_mode,
    speech_to_text, sensitive_word_avoidance, retriever_resource,
    dataset_query_variable, prompt_type, chat_prompt_config, completion_prompt_config,
    dataset_configs, external_data_tools, file_upload, text_to_speech,
    created_by, updated_by)
VALUES (
    '{CONFIG_ID}',
    '{APP_ID}',
    '{model_config["model"]["provider"]}',
    '{model_config["model"]["name"]}',
    NULL,
    NOW(), NOW(),
    '{model_config["opening_statement"].replace("'", "''")}',
    '{sql_json(model_config["suggested_questions"])}',
    '{sql_json(model_config["suggested_questions_after_answer"])}',
    '{sql_json(model_config["more_like_this"])}',
    '{sql_json(model_config["model"])}',
    '{sql_json(model_config["user_input_form"])}',
    '{model_config["pre_prompt"].replace("'", "''")}',
    '{sql_json(model_config["agent_mode"])}',
    '{sql_json(model_config["speech_to_text"])}',
    '{sql_json(model_config["sensitive_word_avoidance"])}',
    '{sql_json(model_config["retriever_resource"])}',
    '',
    '{model_config["prompt_type"]}',
    '{sql_json(model_config["chat_prompt_config"])}',
    '{sql_json(model_config["completion_prompt_config"])}',
    '{sql_json(model_config["dataset_configs"])}',
    '{sql_json(model_config["external_data_tools"])}',
    '{sql_json(model_config["file_upload"])}',
    '{sql_json(model_config["text_to_speech"])}',
    '{ACCOUNT_ID}', '{ACCOUNT_ID}'
);
"""

# 3. Link app to config
update_app_sql = f"""
UPDATE apps SET app_model_config_id = '{CONFIG_ID}' WHERE id = '{APP_ID}';
"""

# 4. Create an API token for the app
TOKEN_ID = str(uuid.uuid4())
TOKEN = f"app-{uuid.uuid4().hex[:24]}"
insert_token_sql = f"""
INSERT INTO api_tokens (id, app_id, tenant_id, token, type, created_by)
VALUES ('{TOKEN_ID}', '{APP_ID}', '{TENANT_ID}', '{TOKEN}', 'app', '{ACCOUNT_ID}');
"""

# Write SQL to file for review
sql = insert_app_sql + "\n" + insert_config_sql + "\n" + update_app_sql + "\n" + insert_token_sql
with open("agent/_import.sql", "w") as f:
    f.write(sql)

print(f"APP_ID: {APP_ID}")
print(f"CONFIG_ID: {CONFIG_ID}")
print(f"TOKEN: {TOKEN}")
print(f"SQL written to agent/_import.sql")
