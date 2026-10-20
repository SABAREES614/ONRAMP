"""ONRAMP coded tools (deterministic Python tools invoked by Neuro-SAN agents).

Resolved by the neuro-san server via AGENT_TOOL_PATH=src and the HOCON
``"class": "onramp.<module>.<Class>"`` references. Each tool subclasses
``neuro_san.interfaces.coded_tool.CodedTool`` and reads sensitive values from
``sly_data`` so they never enter the LLM prompt/chat stream.
"""
