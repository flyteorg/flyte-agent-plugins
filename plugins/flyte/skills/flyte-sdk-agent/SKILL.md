---
name: flyte-sdk-agent
description: 'Builds durable agents with Flyte 2 — ReAct patterns, Plan-and-Execute, LangGraph integration, PydanticAI integration, OpenAI Agents SDK integration, agent memory, MCP tool integration, skills, and agent chat UI. Use when the user wants to build AI agents, implement ReAct loops, integrate agent frameworks, add agent memory, or build agent-powered workflows. Trigger words: "agent", "ReAct", "LangGraph", "PydanticAI", "OpenAI agents", "MCP", "tool calling", "memory", "skills", "agentic".'
---

# Flyte 2 SDK Agent Skill

Build durable, observable AI agents with Flyte 2.

## Grounding References

| Resource | URL |
|---|---|
| Official docs | https://www.union.ai/docs/v2/flyte |
| Docs index (LLMs) | https://www.union.ai/docs/v2/flyte/llms.txt |
| SDK API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-sdk/ |
| CLI API reference | https://www.union.ai/docs/v2/union/api-reference/flyte-cli/ |
| flyte-sdk source | https://github.com/flyteorg/flyte-sdk |
| Example code | https://github.com/unionai/unionai-examples |
| Flyte MCP tools | Available via the `flyte-cluster` and `flyte-docs` MCP servers |

## Pure Python Agents (No Framework)

### ReAct Pattern — Reason, Act, Observe

```python
import flyte

env = flyte.TaskEnvironment(
    name="react-agent",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "openai", "boto3",
    ),
)

@env.task
async def think(observation: str) -> str:
    """LLM generates next action."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"Observation: {observation}\nWhat do you do next?"},
        ],
    )
    return response.choices[0].message.content

@env.task
async def act(thought: str) -> dict:
    """Parse thought and execute tool call."""
    # Parse the thought to extract tool name and arguments
    # Then call the appropriate tool
    return {"tool": "search", "result": "search results..."}

@env.task
async def observe(result: dict) -> str:
    """Format tool result for the next reasoning step."""
    return f"Tool {result['tool']} returned: {result['result']}"

@env.task
async def react_loop(initial_query: str, max_steps: int = 5) -> str:
    """ReAct loop: think → act → observe → think → ..."""
    observation = initial_query
    for i in range(max_steps):
        thought = await think(observation)
        if "FINAL_ANSWER" in thought:
            return thought.split("FINAL_ANSWER:")[-1].strip()
        result = await act(thought)
        observation = await observe(result)
    return "Max steps reached"

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(react_loop("What is the weather in Tokyo?"))
    print(result)
```

### Plan-and-Execute with Parallel Fan-out

```python
@env.task
async def plan(query: str) -> list[str]:
    """Generate a plan of sub-tasks."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Break this query into sub-tasks."},
            {"role": "user", "content": query},
        ],
    )
    # Parse response into list of sub-tasks
    return response.choices[0].message.content.split("\n")

@env.task
async def execute_subtask(task: str) -> str:
    """Execute a single sub-task."""
    ...
    return result

@env.task
async def synthesize(results: list[str]) -> str:
    """Synthesize results into a final answer."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Synthesize these results."},
            {"role": "user", "content": "\n".join(results)},
        ],
    )
    return response.choices[0].message.content

@env.task
async def plan_and_execute(query: str) -> str:
    """Plan sub-tasks, execute in parallel, synthesize results."""
    tasks = await plan(query)
    # Parallel execution of sub-tasks
    results = await flyte.map(execute_subtask, tasks)
    return await synthesize(results)
```

## Agent Framework Integrations

### LangGraph Agents

```python
import flyte
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

env = flyte.TaskEnvironment(
    name="langgraph-agent",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "langgraph", "langchain-openai", "langchain",
    ),
)

@env.task
async def langgraph_agent(query: str) -> str:
    """Run a LangGraph agent as a Flyte task."""
    agent = create_react_agent(
        model=ChatOpenAI(model="gpt-4"),
        tools=[search_tool, calculate_tool],
    )
    result = agent.invoke({"messages": [("user", query)]})
    return result["messages"][-1].content

@env.task
async def parallel_agents(queries: list[str]) -> list[str]:
    """Run multiple LangGraph agents in parallel."""
    results = await flyte.map(langgraph_agent, queries)
    return results
```

### PydanticAI Agents

```python
import flyte
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    confidence: float
    recommendations: list[str]

env = flyte.TaskEnvironment(
    name="pydantic-agent",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "pydantic-ai", "openai",
    ),
)

@env.task
async def pydantic_agent(query: str) -> AnalysisResult:
    """Run a PydanticAI agent with structured output."""
    agent = Agent(
        "openai:gpt-4",
        result_type=AnalysisResult,
    )
    result = await agent.run(query)
    return result.data

@env.task
async def parallel_pydantic_agents(queries: list[str]) -> list:
    """Run multiple PydanticAI agents in parallel."""
    results = await flyte.map(pydantic_agent, queries)
    return results
```

### OpenAI Agents SDK

```python
import flyte
from openai.agents import Agent, Tool

env = flyte.TaskEnvironment(
    name="openai-agent",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "openai",
    ),
)

@env.task
async def search_tool(query: str) -> str:
    """A tool that is also a durable Flyte task."""
    # Tools become durable — results are cached and replayable
    ...
    return results

@env.task
async def openai_agent(query: str) -> str:
    """Run an OpenAI Agents SDK agent."""
    agent = Agent(
        name="researcher",
        instructions="Research the query thoroughly.",
        tools=[search_tool],
    )
    result = agent.run(query)
    return result.final_output

@env.task
async def main(query: str) -> str:
    """Wrap the agent in a Flyte workflow for durability."""
    return await openai_agent(query)
```

## Building Agents with Flyte Primitives

### How Flyte maps to the agent stack

| Agent Concept | Flyte Primitive |
|---|---|
| Tool call | `@env.task` — each tool is a durable task |
| Reasoning step | `@env.task` with LLM call |
| Observation | Output of tool task → input to reasoning task |
| Loop | `flyte.condition` for external gates, or dynamic workflows for internal loops |
| Parallel execution | `flyte.map` for fan-out sub-tasks |
| Traces | `flyte.trace` for lightweight LLM calls within a step |

### Durable agent pattern

```python
@env.task
async def llm_call(prompt: str, model: str = "gpt-4") -> str:
    """Durable LLM call — cached by input, replayable."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content

@env.task
async def tool_call(tool_name: str, args: dict) -> str:
    """Durable tool execution — each tool call is a Flyte action."""
    if tool_name == "search":
        return perform_search(args["query"])
    elif tool_name == "calc":
        return str(evaluate(args["expression"]))
    raise ValueError(f"Unknown tool: {tool_name}")

@env.task
async def agent_step(
    history: list[dict],
) -> dict:
    """Single agent step: decide next action."""
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Decide next action based on history."},
            *history,
        ],
        response_format={"type": "json_object"},
    )
    return eval(response.choices[0].message.content)  # parse JSON

@env.task
async def run_agent(
    query: str,
    max_steps: int = 10,
) -> str:
    """Run a durable agent loop."""
    history = [{"role": "user", "content": query}]

    for step in range(max_steps):
        decision = await agent_step(history)
        if decision["type"] == "final_answer":
            return decision["answer"]

        # Execute tool
        result = await tool_call(decision["tool"], decision["args"])
        history.append({"role": "assistant", "content": f"Tool {decision['tool']} → {result}"})

    return "Max steps reached"
```

## Agent Memory

### Keyed MemoryStore

```python
import flyte
from flyte.extend import MemoryStore

env = flyte.TaskEnvironment(
    name="agent-with-memory",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "openai",
    ),
)

@env.task
async def agent_with_memory(query: str, user_id: str) -> str:
    """Agent with persistent memory per user."""
    memory = MemoryStore(keyed_by=user_id)

    # Load previous context
    context = await memory.get("conversation", default=[])

    # Add new message
    context.append({"role": "user", "content": query})

    # Generate response
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4",
        messages=context,
    )
    answer = response.choices[0].message.content

    # Store updated context
    context.append({"role": "assistant", "content": answer})
    await memory.set("conversation", context)

    return answer
```

### Run-level context

```python
@env.task
async def agent_step(query: str) -> str:
    """Access run-level context for memory."""
    ctx = flyte.ctx()

    # Use run ID as a key for temporary memory
    run_memory_key = f"run:{ctx.run_id}:memory"

    # Store intermediate results
    ...
```

## Agent Chat UI

### Built-in chat UI

```python
import flyte
from flyte.extend import Agent, tool

env = flyte.TaskEnvironment(
    name="chat-agent",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "openai",
    ),
)

class ChatAgent(Agent):
    """Built-in agent with chat UI."""

    @tool
    async def search(self, query: str) -> str:
        """Search the web."""
        ...

    @tool
    async def calculate(self, expression: str) -> str:
        """Evaluate a math expression."""
        ...

    async def run(self, message: str) -> str:
        """Main agent loop."""
        # Use tools to respond
        return "Response"

if __name__ == "__main__":
    flyte.init_from_config()
    agent = ChatAgent()
    agent.run(message="Hello!")
```

### Custom FastAPI chat app

```python
from fastapi import FastAPI
import flyte
from flyte.app.extras import FastAPIAppEnvironment

app = FastAPI()
env = FastAPIAppEnvironment(
    name="chat-app",
    app=app,
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastapi", "uvicorn", "openai",
    ),
)

@app.post("/chat")
async def chat(message: str):
    """Chat endpoint — delegates to a Flyte agent task."""
    result = await flyte.run(agent_task, inputs={"message": message})
    return {"response": result.outputs}

if __name__ == "__main__":
    flyte.init_from_config()
    flyte.serve(env)
```

## Deploying Agents

### As a task

```bash
# Run agent as a one-shot task
flyte run agent.py run_agent --query "Research X"
```

### As a scheduled task (Trigger)

```bash
# Create a trigger for periodic agent execution
flyte trigger create agent_task \
  --cron "0 9 * * 1"  # every Monday at 9am
```

### Behind a webhook

```python
# Agent behind a webhook app
@app.post("/agent")
async def agent_webhook(payload: dict):
    flyte.run(agent_task, inputs={"message": payload["text"]})
    return {"status": "queued"}
```

### Chat app pattern

```bash
# Deploy as a persistent app
flyte deploy agent_app.py env
```

## MCP Integration

### Building an MCP server for agents

```python
import flyte
from flyte.extend import MCPServer, tool

env = flyte.TaskEnvironment(
    name="mcp-server",
    image=flyte.Image.from_debian_base(python_version=(3, 12)).with_pip_packages(
        "fastmcp",
    ),
)

@env.task
async def build_mcp_server() -> MCPServer:
    """Build an MCP server with durable tools."""

    @tool
    async def search(query: str) -> str:
        return perform_search(query)

    @tool
    async def fetch(url: str) -> str:
        return fetch_url(url)

    return MCPServer(tools=[search, fetch])
```

### Connecting an MCP client

```python
# Claude Code — local (stdio)
# Configure inClaude Code settings to connect to the Flyte MCP server

# OpenCode — local
# Configure in opencode.json to connect to the Flyte MCP server
```

## Agent Anti-Patterns

1. **Don't put LLM calls in a loop without durability** — each LLM call should be a `@env.task` for caching and replay.
2. **Don't use Union-only features** — avoid `ReusePolicy` and other Union-specific APIs.
3. **Don't pass large prompts inline** — use `flyte.File` for large context windows.
4. **Don't forget to set resources** — LLM agent tasks need CPU for the orchestration container.
5. **Don't hardcode API keys** — use Flyte secrets for LLM API keys.
