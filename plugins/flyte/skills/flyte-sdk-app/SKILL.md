---
name: flyte-sdk-app
description: 'Builds and serves Flyte 2 apps — FastAPI, Streamlit, vLLM, SGLang, WebSocket, and browser apps. Use when the user wants to serve a model, create a REST API, build a dashboard, deploy an LLM backend, or create a web app with Flyte. Trigger words: "app", "serve", "deploy app", "FastAPI", "Streamlit", "vLLM", "SGLang", "REST API", "dashboard", "serving", "endpoint", "webhook", "WebSocket".'
---

# Flyte 2 SDK App Skill

Build and serve applications with Flyte 2.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via `flyte-mcp` server |

## App Types

| App Type | Use Case | Import |
|---|---|---|
| `FastAPIAppEnvironment` | REST APIs, model serving | `from flyte.app.extras import FastAPIAppEnvironment` |
| `StreamlitAppEnvironment` | Dashboards, data apps | `from flyte.app.extras import StreamlitAppEnvironment` |
| `vLLMAppEnvironment` | LLM serving | `from flyte.app.extras import vLLMAppEnvironment` |
| `SGLangAppEnvironment` | Structured generation | `from flyte.app.extras import SGLangAppEnvironment` |
| Custom (`AppEnvironment`) | Any HTTP server | `import flyte` |

## FastAPI App — Model Serving

### Basic FastAPI app

```python
from fastapi import FastAPI
import flyte
from flyte.app.extras import FastAPIAppEnvironment

app = FastAPI()
env = FastAPIAppEnvironment(
    name="my-model",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "torch",
    ),
)

@app.get("/predict")
async def predict(x: float) -> dict:
    return {"result": x * 2 + 5}

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

### Model serving with loading

```python
from fastapi import FastAPI
import flyte
from flyte.app.extras import FastAPIAppEnvironment

app = FastAPI()
env = FastAPIAppEnvironment(
    name="text-classifier",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "torch", "transformers",
    ),
)

model = None  # Loaded once at startup

@app.on_event("startup")
async def load_model():
    global model
    model = transformers.AutoModelForSequenceClassification.from_pretrained("bert-base")

@app.get("/predict")
async def predict(text: str) -> dict:
    assert model is not None
    outputs = model(transformers.encode(text))
    return {"prediction": outputs.argmax().item(), "confidence": outputs.softmax().max().item()}

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

### Multi-file FastAPI app

```
app/
  __init__.py
  main.py        # FastAPI app entry
  routes/
    __init__.py
    predict.py
    health.py
  models/
    __init__.py
    classifier.py
```

```python
# app/main.py
from fastapi import FastAPI
from .routes import predict, health

app = FastAPI()
app.include_router(predict.router, prefix="/api")
app.include_router(health.router, prefix="/health")
```

## Streamlit App — Data Dashboards

### Basic Streamlit app

```python
import streamlit as st
import flyte
from flyte.app.extras import StreamlitAppEnvironment

st.title("Data Dashboard")

df = st.dataframe(load_data())

if st.button("Refresh"):
    st.rerun()

env = StreamlitAppEnvironment(
    name="dashboard",
    script="app.py",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "streamlit", "pandas", "matplotlib",
    ),
)

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

### Streamlit with upstream app dependency

```python
import streamlit as st
import requests
import flyte
from flyte.app.extras import StreamlitAppEnvironment

# Access upstream app endpoint
MODEL_ENDPOINT = flyte.AppEndpoint("model-serving")

st.title("Model Results")

text = st.text_input("Enter text:")
if text:
    response = requests.post(
        f"{MODEL_ENDPOINT.url}/predict",
        json={"text": text},
    )
    st.json(response.json())

env = StreamlitAppEnvironment(
    name="results-dashboard",
    script="app.py",
    depends_on=[MODEL_ENDPOINT],
)
```

## vLLM App — LLM Serving

### Basic vLLM app

```python
import flyte
from flyte.app.extras import vLLMAppEnvironment

env = vLLMAppEnvironment(
    name="llm-serving",
    model="meta-llama/Llama-3-8b-Instruct",
    image=flyte.Image.from_image("vllm/vllm-openai:latest"),
    resources=flyte.Resources(
        cpu="8",
        memory="32Gi",
        gpu="1",
        gpu_model="nvidia-a10g",
    ),
)

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

### vLLM with model prefetch

```python
env = vLLMAppEnvironment(
    name="llm-serving",
    model="meta-llama/Llama-3-8b-Instruct",
    prefetch=True,  # prefetch model weights at deploy time
    image=flyte.Image.from_image("vllm/vllm-openai:latest"),
    resources=flyte.Resources(
        cpu="8",
        memory="32Gi",
        gpu="1",
        gpu_model="nvidia-a10g",
    ),
)
```

### vLLM multi-GPU

```python
env = vLLMAppEnvironment(
    name="llm-serving",
    model="meta-llama/Llama-3-70b-Instruct",
    tensor_parallel_size=4,  # shard across 4 GPUs
    prefetch=True,
    image=flyte.Image.from_image("vllm/vllm-openai:latest"),
    resources=flyte.Resources(
        cpu="16",
        memory="128Gi",
        gpu="4",
        gpu_model="nvidia-a100",
    ),
)
```

## SGLang App — Structured Generation

### Basic SGLang app

```python
import flyte
from flyte.app.extras import SGLangAppEnvironment

env = SGLangEnvironment(
    name="structured-gen",
    model="meta-llama/Llama-3-8b-Instruct",
    prefetch=True,
    image=flyte.Image.from_image("sgl-project/sglang:latest"),
    resources=flyte.Resources(
        cpu="4",
        memory="16Gi",
        gpu="1",
        gpu_model="nvidia-a10g",
    ),
)

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

## WebSocket Apps

```python
import asyncio
import flyte
from flyte.app.extras import FastAPIAppEnvironment
from fastapi import FastAPI, WebSocket

app = FastAPI()
env = FastAPIAppEnvironment(
    name="websocket-app",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "websockets",
    ),
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            result = process(data)
            await websocket.send_text(result)
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

## Serving vs Deploying

### Serve (ephemeral, for development)

```bash
# Serve an app locally
flyte serve app.py env
```

```python
# Serve programmatically
result = flyte.serve(env)
print(f"App URL: {result.url}")
```

### Deploy (persistent, for production)

```bash
# Deploy an app
flyte deploy app.py env
```

```python
# Deploy programmatically
result = flyte.deploy(env)
print(f"App URL: {result.url}")
```

### Activating and deactivating apps

```bash
# Activate a deployed app
flyte activate <app_name> --project flytesnacks --domain development

# Deactivate
flyte deactivate <app_name> --project flytesnacks --domain development

# Check status
flyte app get <app_name> --project flytesnacks --domain development
```

### Using Flyte MCP for app management

Getting an app's status, activating it, and deactivating it are all available as MCP
tools, each taking the app name. The Flyte MCP server exposes this directly. Do not hardcode tool names — MCP
clients namespace them differently (Claude Code renders them as
`mcp__plugin_flyte_flyte-cluster__<tool>`), and the server describes its own tools and
parameters via `tools/list`. Read them from there.


## App Parameters

### Passing parameters into apps

```python
env = FastAPIAppEnvironment(
    name="model-serving",
    app=app,
    parameters={
        "model_name": flyte.Parameter.mount("/models/model.safetensors"),
        "api_key": flyte.Parameter.env_var("API_KEY"),
    },
)
```

### Overriding parameters at serve time

```bash
flyte serve app.py env --parameter model_name=/custom/path
```

## App Autoscaling

### Auto-scaling apps

```python
env = FastAPIAppEnvironment(
    name="auto-scaling-app",
    app=app,
    scaling=flyte.ScalingConfig(
        min_replicas=1,
        max_replicas=10,
        target_cpu_utilization=70,
        idle_ttl="5m",
        scale_down_delay="10m",
    ),
)
```

## App Dependencies (Serving Graphs)

### Deploying multiple apps together

```python
model_env = FastAPIAppEnvironment(
    name="model-serving",
    app=model_app,
    image=model_image,
)

dashboard_env = StreamlitAppEnvironment(
    name="results-dashboard",
    script="dashboard.py",
    depends_on=[model_env],  # upstream dependency
    image=dashboard_image,
)

# Deploy both together
flyte.deploy(model_env)
flyte.deploy(dashboard_env)

# Access upstream endpoint
model_url = model_env.endpoint.url
```

### GPU/CPU split serving graph

```python
# GPU app: model inference
gpu_env = FastAPIAppEnvironment(
    name="model-gpu",
    app=gpu_app,
    image=flyte.Image.from_image("nvidia/cuda:12.1-py3").with_pip_packages(
        "torch", "fastapi", "uvicorn",
    ),
    resources=flyte.Resources(
        cpu="4", memory="16Gi", gpu="1", gpu_model="nvidia-a10g",
    ),
)

# CPU app: pre/post processing
cpu_env = FastAPIAppEnvironment(
    name="preprocess-cpu",
    app=cpu_app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "pillow", "numpy",
    ),
    depends_on=[gpu_env],
    resources=flyte.Resources(cpu="2", memory="4Gi"),
)
```

## Webhook Apps

### Basic webhook

```python
import flyte
from flyte.app.extras import FastAPIAppEnvironment
from fastapi import FastAPI, Request

app = FastAPI()
env = FastAPIAppEnvironment(
    name="webhook-receiver",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn",
    ),
)

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    # Trigger a Flyte workflow
    flyte.run(process_webhook, inputs={"payload": payload})
    return {"status": "received"}

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

## App Secrets

### Secret-based authentication

```python
# Create a secret (via CLI or SDK)
# flyte secret create my-api-key --value "sk-xxx"

env = FastAPIAppEnvironment(
    name="authenticated-app",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn",
    ),
    secrets={"api_key": flyte.Secret(key="my-api-key", group="default")},
)

# Access secret inside the app
api_key = os.environ["FLYTE_SECRET_MY_API_KEY"]
```

## Anti-Patterns

1. **Don't use `flyte.run()` inside apps** — use `flyte.serve()` for apps, `flyte.run()` for workflows.
2. **Don't forget `flyte.init_from_config()`** — required before `flyte.serve()`.
3. **Don't hardcode model paths** — use `flyte.AppEndpoint` for upstream app URLs.
4. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
5. **Don't serve GPU apps without GPU resources** — always specify `gpu` and `gpu_model` in resources.
