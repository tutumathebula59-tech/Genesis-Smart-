# assistant_backend.py
#
# Add this to your FastAPI hub (app/main.py) to power the "Assistant" tab.
# It receives a chat message + the current device list from the frontend,
# lets Claude decide what (if anything) to change, actually applies those
# changes to your real devices, and returns a natural-language reply plus
# the actions taken so the frontend can update its UI state.
#
# Setup:
#   pip install anthropic
#   export ANTHROPIC_API_KEY=sk-ant-...        (keep this OFF the frontend)
#
# Wire into your existing app:
#   from assistant_backend import router as assistant_router
#   app.include_router(assistant_router)

import os
import json
from fastapi import APIRouter
from pydantic import BaseModel
from anthropic import Anthropic

router = APIRouter()
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-5-5"

class Device(BaseModel):
    id: str
    name: str
    type: str
    online: bool
    state: dict

class ChatRequest(BaseModel):
    message: str
    devices: list[Device]
    history: list[dict] = []   # optional: [{role: "user"|"assistant", content: str}, ...]

TOOLS = [
    {
        "name": "control_device",
        "description": "Change a property on a device's state, e.g. turning a light on/off, "
                        "locking/unlocking a lock, or setting brightness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "The device's id, e.g. 'light_living'."},
                "key": {"type": "string", "description": "The state field to change, e.g. 'on', 'locked', 'brightness'."},
                "value": {"description": "The new value for that field (boolean, number, or string)."},
            },
            "required": ["device_id", "key", "value"],
        },
    },
    {
        "name": "set_device_online",
        "description": "Bring a device online (connect) or take it offline (disconnect).",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "online": {"type": "boolean"},
            },
            "required": ["device_id", "online"],
        },
    },
]

def apply_control_device(device_id: str, key: str, value):
    """
    Replace this with your real device control logic — e.g. publish an
    MQTT message, call a GPIO library, or hit a smart-plug's local API.
    This is also where you should validate device_id/key against your
    actual device registry before acting on anything.
    """
    try:
        from hub_core import command_sync   # imported here to avoid a circular import
        command_sync(device_id, key, value)
    except Exception as ex:
        return {"error": str(getattr(ex, "detail", ex))}
    return {"device_id": device_id, "key": key, "value": value}

def apply_set_online(device_id: str, online: bool):
    # Example: mark device reachable/unreachable in your device registry/db
    return {"device_id": device_id, "online": online}

@router.post("/assistant/chat")
def assistant_chat(req: ChatRequest):
    device_summary = "\n".join(
        f"- {d.id} ({d.name}, type={d.type}, online={d.online}, state={d.state})"
        for d in req.devices
    )
    system = (
        "You are the voice/chat assistant for a home IoT hub. "
        "You can inspect and control the devices listed below by calling tools. "
        "Only act on devices that exist in this list. Keep replies short and conversational "
        "(one or two sentences), suitable for a chat bubble or being read aloud.\n\n"
        f"Current devices:\n{device_summary}"
    )

    messages = req.history + [{"role": "user", "content": req.message}]
    actions = []
    online_change = None

    # Agentic loop: keep going until Claude stops calling tools
    for _ in range(5):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            reply_text = "".join(b.text for b in response.content if b.type == "text")
            return {"reply": reply_text, "actions": actions, "online": online_change}

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "control_device":
                result = apply_control_device(**block.input)
                if "error" not in result:
                    actions.append({"id": result["device_id"], "key": result["key"], "value": result["value"]})
            elif block.name == "set_device_online":
                result = apply_set_online(**block.input)
                online_change = {"id": result["device_id"], "value": result["online"]}
            else:
                result = {"error": f"unknown tool {block.name}"}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })
        messages.append({"role": "user", "content": tool_results})

    return {"reply": "Sorry, that took too many steps — try rephrasing.", "actions": actions, "online": online_change}
