#!/usr/bin/env python3
"""MCP Server: text-to-speech-mcp - Text to Speech using Microsoft Edge TTS"""

import sys
import json
import asyncio
import base64
import edge_tts
import uuid
import traceback


def log(msg):
    """Log to stderr so it doesn't interfere with MCP stdio transport."""
    print(f"[TTS-MCP] {msg}", file=sys.stderr, flush=True)


async def text_to_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> dict:
    """
    Convert text to speech using Microsoft Edge TTS.

    Args:
        text: Text to convert to speech
        voice: Voice name (e.g., zh-CN-XiaoxiaoNeural, en-US-JennyNeural, ja-JP-NanamiNeural)

    Returns:
        dict with 'audio_base64' (WAV PCM data as base64) and 'format' keys
    """
    log(f"TTS request: voice={voice}, text='{text[:80]}{'...' if len(text) > 80 else ''}'")

    try:
        # Generate unique filename for temporary storage
        tmp_path = f"/tmp/tts_output_{uuid.uuid4().hex}.mp3"

        # Use edge-tts to generate speech
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)

        # Read the audio file and encode as base64
        with open(tmp_path, "rb") as f:
            audio_data = f.read()

        # Clean up temp file
        import os
        os.remove(tmp_path)

        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        log(f"TTS success: {len(audio_data)} bytes generated")

        return {
            "success": True,
            "data": {
                "audio_base64": audio_b64,
                "format": "audio/mpeg",
                "duration_seconds": None,
                "voice": voice,
                "characters": len(text)
            }
        }

    except Exception as e:
        log(f"TTS error: {str(e)}")
        log(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


def handle_request(request: dict) -> dict:
    """
    Handle a single MCP request (JSON-RPC style).
    """
    method = request.get("method", "")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "protocolVersion": "0.1.0",
                "serverInfo": {
                    "name": "text-to-speech-mcp",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {}
                }
            }
        }

    elif method == "listTools":
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "tools": [
                    {
                        "name": "text_to_speech",
                        "description": "将文本转换为自然语音，支持中文/英文/日文等20+语言和多种音色。Use Microsoft Edge TTS engine.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "要转换为语音的文本内容 (Text to convert to speech)"
                                },
                                "voice": {
                                    "type": "string",
                                    "description": "语音音色名称。常用: zh-CN-XiaoxiaoNeural (中文女声), zh-CN-YunxiNeural (中文男声), en-US-JennyNeural (英文女声), en-US-GuyNeural (英文男声), ja-JP-NanamiNeural (日文女声), ko-KR-SunHiNeural (韩文女声), fr-FR-DeniseNeural (法文女声)",
                                    "default": "zh-CN-XiaoxiaoNeural"
                                }
                            },
                            "required": ["text"]
                        }
                    }
                ]
            }
        }

    elif method == "callTool":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name == "text_to_speech":
            text = tool_args.get("text", "")
            voice = tool_args.get("voice", "zh-CN-XiaoxiaoNeural")

            if not text:
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32000,
                        "message": "text parameter is required"
                    }
                }

            # Run async function synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(text_to_speech(text, voice))
            finally:
                loop.close()

            if result.get("success"):
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result["data"], ensure_ascii=False)
                            }
                        ]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32000,
                        "message": result.get("error", "Unknown error")
                    }
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32601,
                    "message": f"Tool not found: {tool_name}"
                }
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


def main():
    """Main loop: read JSON-RPC requests from stdin, write responses to stdout."""
    log("TTS MCP Server starting...")
    log(f"Python version: {sys.version}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            log(f"Received request: {request.get('method', 'unknown')}")
            response = handle_request(request)
            response_str = json.dumps(response, ensure_ascii=False)
            sys.stdout.write(response_str + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            log(f"JSON parse error: {e}")
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(e)}"}
            }) + "\n")
            sys.stdout.flush()
        except Exception as e:
            log(f"Unhandled error: {e}")
            log(traceback.format_exc())
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
