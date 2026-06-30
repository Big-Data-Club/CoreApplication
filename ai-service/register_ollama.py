import asyncio
import sys
import logging

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("register_ollama")

try:
    from app.core.llm_gateway.registry import get_registry
    from app.core.llm_gateway.types import TASK_CHAT, TASK_AGENT_REACT, TASK_DIAGNOSIS
except ImportError:
    logger.error("Could not import app.core.llm_gateway. Make sure you run this script inside the ai-service workspace or container.")
    sys.exit(1)

async def main():
    registry = get_registry()
    
    provider_code = "ollama_self_hosted"
    model_name = "llama3:latest"
    base_url = "https://ollama.convolution-nguyen-anh-duong.id.vn"
    
    logger.info("Step 1: Upserting LLM Provider...")
    provider = await registry.upsert_provider(
        code=provider_code,
        display_name="Ollama Self Hosted",
        adapter_type="ollama",  # Maps to OpenAICompatAdapter which speaks OpenAI protocol
        base_url=base_url,
        enabled=True,
    )
    logger.info(f"Provider '{provider.code}' upserted successfully (ID: {provider.id}).")

    logger.info("Step 2: Guaranteeing encrypted dummy API key...")
    existing_keys = await registry.list_api_keys(provider_id=provider.id)
    if not any(k.alias == "dummy-key" for k in existing_keys):
        # We write a dummy key because the Gateway requires at least one active key to lease.
        # This dummy key is encrypted properly using the server's master Fernet key.
        key = await registry.create_api_key(
            provider_id=provider.id,
            alias="dummy-key",
            plaintext_key="dummy-value-not-used-by-ollama",
        )
        logger.info(f"API key created with alias '{key.alias}' (ID: {key.id}).")
    else:
        logger.info("API key 'dummy-key' already exists.")

    logger.info("Step 3: Registering Model with Cloudflare Access headers...")
    model_config = {
        "headers": {
            "CF-Access-Client-Id": "ec100a482ef8342ec79ed75c633a736f.access",
            "CF-Access-Client-Secret": "a0353b5bffacff5a0448c5161c10994e64a44ede6ef4ca6b635dd4435aed0d0c"
        }
    }
    
    model = await registry.upsert_model(
        provider_id=provider.id,
        model_name=model_name,
        display_name="Llama 3 Latest (Self Hosted)",
        family="llama",
        context_window=8192,
        supports_json=True,
        supports_tools=False,
        supports_streaming=True,
        supports_vision=False,
        input_cost_per_1k=0.0,
        output_cost_per_1k=0.0,
        default_temperature=0.3,
        default_max_tokens=2048,
        enabled=True,
        config=model_config
    )
    logger.info(f"Model '{model.model_name}' upserted successfully (ID: {model.id}).")

    logger.info("Step 4: Binding Model to LLM Tasks (diagnosis)...")
    target_tasks = [TASK_DIAGNOSIS]

    
    for task in target_tasks:
        binding = await registry.upsert_binding(
            task_code=task,
            model_id=model.id,
            priority=1,      # priority 1 places it first in the fallback chain
            pinned=True,     # pinned = True makes it the exclusive model for this task
            enabled=True,
            notes=f"Bound to self-hosted Ollama model {model_name} via Cloudflare Access."
        )
        logger.info(f"Binding for task '{task}' created/updated successfully (ID: {binding.id}).")

    logger.info("Registration complete! All tasks successfully bound to your self-hosted LLM.")

if __name__ == "__main__":
    asyncio.run(main())
