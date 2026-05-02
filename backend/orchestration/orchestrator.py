import json
import logging
import re
from typing import Any

from core.auth import get_oauth_token
from core.runner import run_turn
from agents.registry import AGENT_FACTORIES
from orchestration.tools import (
    delete_generated_code_file,
    list_generated_code_files,
    load_generated_code_file,
    load_spec,
    patch_generated_code_file,
    rename_generated_code_file,
    save_nontech_artifacts,
    save_technical_artifacts,
    set_project_stage,
    submit_spec,
)
from orchestration.store import Stage, get_or_create_project, persist_project


class Orchestrator:
    def _build_response(self, proj, reply: str, artifacts_md: dict[str, str] | None = None, generated_code_files: dict[str, str] | None = None) -> dict[str, Any]:
        
        # handle parsing of reply if it's a JSON string, otherwise return raw string
        try:
            # use regex to extract JSON from md code block if it exists, otherwise use raw reply
            # consider case sensitive in regex to allow for ```json or ```JSON
            md_code_block_match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL | re.IGNORECASE)
            if md_code_block_match:
                parsed_reply = json.loads(md_code_block_match.group(1))
                reply = json.dumps(parsed_reply)  # Ensure reply is a JSON string
            else:
                json_match = re.search(r'\{.*\}', reply, re.DOTALL)
                if json_match:
                    parsed_reply = json.loads(json_match.group())
                    reply = json.dumps(parsed_reply)  # Ensure reply is a JSON string
        except json.JSONDecodeError:
            logging.warning(f"Failed to parse agent reply as JSON, returning raw string. Reply: {reply}")

        return {
            "stage": proj.stage,
            "reply": reply,
            "spec": proj.spec,
            "nontech_artifacts_md": proj.nontech_artifacts_md,
            "technical_artifacts_md": proj.technical_artifacts_md,
            "artifacts_md": artifacts_md or proj.technical_artifacts_md or proj.nontech_artifacts_md,
            "generated_code_files": generated_code_files or proj.generated_code_files,
        }

    def _requirements_tools(self) -> list:
        return [submit_spec]

    def _artifacts_tools(self) -> list:
        return [load_spec, save_nontech_artifacts, save_technical_artifacts]

    def _code_generation_tools(self) -> list:
        return [load_spec, list_generated_code_files, load_generated_code_file, patch_generated_code_file, delete_generated_code_file, rename_generated_code_file]
    
    def _qa_tools(self) -> list:
        return [load_spec, list_generated_code_files, load_generated_code_file, patch_generated_code_file, delete_generated_code_file, rename_generated_code_file]

    async def _handle_wait_approval(self, project_id: str, req_session_id: str, normalized: str) -> dict[str, Any]:
        proj = get_or_create_project(project_id, req_session_id)
        if normalized == "approve":
            set_project_stage(project_id, Stage.TECH_ARTIFACTS)
            return {}
        if normalized == "change":
            set_project_stage(project_id, Stage.REQ)
            proj = get_or_create_project(project_id, req_session_id)
            return self._build_response(
                proj=proj,
                reply='{"message": "You have entered revision mode. Please enter the points to be modified."}',
                artifacts_md=proj.nontech_artifacts_md,
            )
        return self._build_response(
            proj=proj,
            reply='{"message": "approve or change"}',
            artifacts_md=proj.nontech_artifacts_md,
        )

    async def _run_requirements(self, token, project_id: str, req_session_id: str, user_message: str) -> dict[str, Any]:
        proj = get_or_create_project(project_id, req_session_id)
        req_agent = AGENT_FACTORIES["requirements"](token, tools=self._requirements_tools())
        phase = "requirements_revision" if proj.nontech_artifacts_md else "requirements_gathering"
        req_prompt = (
            f"project_id={project_id}\n"
            f"phase={phase}\n"
            "Continue requirements gathering for this project.\n"
            f"User message:\n{user_message}"
        )
        reply = await run_turn(req_agent, req_session_id, message=req_prompt)
        proj = get_or_create_project(project_id, req_session_id)

        if proj.stage == Stage.ARTIFACTS_NON_TECH and proj.spec:
            return await self._run_artifacts_non_tech(token, project_id, req_session_id)

        return self._build_response(proj=proj, reply=reply)

    async def handle(self, project_id: str, req_session_id: str, user_message: str) -> dict:
        proj = get_or_create_project(project_id, req_session_id)
        normalized = user_message.strip().lower()

        # Approval gate does not need an LLM call.
        if proj.stage == Stage.WAIT_APPROVAL:
            approval_result = await self._handle_wait_approval(project_id, req_session_id, normalized)
            if approval_result:
                return approval_result
            proj = get_or_create_project(project_id, req_session_id)

        # Remaining stages are model-backed.
        token = await get_oauth_token()

        if proj.stage == Stage.REQ:
            return await self._run_requirements(token, project_id, req_session_id, user_message)
        if proj.stage == Stage.ARTIFACTS_NON_TECH:
            return await self._run_artifacts_non_tech(token, project_id, req_session_id)
        if proj.stage == Stage.TECH_ARTIFACTS:
            return await self._run_artifacts_technical(token, project_id, req_session_id)            
        if proj.stage == Stage.CODEGEN:
            return await self._run_code_generation(token, project_id, req_session_id)
        if proj.stage == Stage.QA:
            return await self._run_qa(token, project_id, req_session_id, user_message)

        return self._build_response(
            proj=proj,
            reply='{"message": "Project complete. Ready for QA."}',
        )

    async def _run_artifacts_non_tech(self, token, project_id: str, req_session_id: str) -> dict:
        art_agent = AGENT_FACTORIES["artifacts"](token, tools=self._artifacts_tools(), phase="non_tech")
        art_prompt = (
            f"project_id={project_id}\n"
            "phase=non_tech\n"
            "Generate PM-facing non-technical artifacts now.\n"
            "Save full content via save_nontech_artifacts(project_id, artifacts_dict) as a dictionary with filename keys and markdown content values, "
        )
        raw_reply = await run_turn(art_agent, session_id=f"{req_session_id}-nontech", message=art_prompt)
        proj = get_or_create_project(project_id, req_session_id)

        if proj.stage == Stage.WAIT_APPROVAL:
            reply = '{"message": "Non-technical artifacts generated successfully and awaiting approval."}'
        else:
            reply = '{"message": "Non-technical artifacts generation failed. Please try again.", "error": ' + raw_reply + '}'
            # proj.stage = Stage.REQ  # Revert stage if save was not successful

        return self._build_response(
            proj=proj,
            reply=reply,
            artifacts_md=proj.nontech_artifacts_md,
        )

    async def _run_artifacts_technical(self, token, project_id: str, req_session_id: str) -> dict:
        art_agent = AGENT_FACTORIES["artifacts"](token, tools=self._artifacts_tools(), phase="technical")
        art_prompt = (
            f"project_id={project_id}\n"
            "phase=technical\n"
            "Generate technical artifacts now. "
            "Use load_spec(project_id) first, then save_technical_artifacts with a dictionary (filename keys, markdown content values) at the end."
        )
        _raw_reply = await run_turn(art_agent, session_id=f"{req_session_id}-tech", message=art_prompt)
        proj = get_or_create_project(project_id, req_session_id)
        reply = '{"message": ' + (
            '"Technical artifacts saved."'
            if proj.stage in {Stage.CODEGEN, Stage.QA}
            else '"Technical artifacts generation did not complete tool save."'
        ) + '}'
        return self._build_response(
            proj=proj,
            reply=reply,
            artifacts_md=proj.technical_artifacts_md,
        )

    async def _run_code_generation(self, token, project_id: str, req_session_id: str) -> dict:
        try:
            code_agent = AGENT_FACTORIES["code_generation"](token, tools=self._code_generation_tools())
            code_prompt = (
                f"project_id={project_id}\n"
                "Generate a POC-level Angular frontend code now.\n"
                "Use tools to get requirements and artifacts, "
                "generate modular Angular components and services with mocked API calls, "
            )
            _raw_reply = await run_turn(code_agent, session_id=f"{req_session_id}-codegen", message=code_prompt)
            print(f"[CODEGEN] Raw agent reply: {_raw_reply}")
            proj = get_or_create_project(project_id, req_session_id)
            
            # Check if code generation was successful
            if proj.generated_code_files:
                reply = '{"message": "Angular frontend code generated successfully."}'
                set_project_stage(proj.project_id, Stage.QA)  # Move to QA stage after successful code generation
                persist_project(project_id)
                return self._build_response(
                    proj=proj,
                    reply=reply,
                    generated_code_files=proj.generated_code_files,
                )
            else:
                reply = '{"message": "Code generation did not complete tool save."}'
                return self._build_response(
                    proj=proj,
                    reply=reply,
                )
        except Exception as e:
            proj = get_or_create_project(project_id, req_session_id)
            error_message = f"Code generation failed: {str(e)}"
            reply = '{"message": "' + error_message + '"}'
            print(f"[ERROR] Code generation: {error_message}")
            # Do not change stage on error - return current project state
            return self._build_response(
                proj=proj,
                reply=reply,
            )

    async def _run_qa(self, llm, project_id: str, req_session_id: str, user_message: str) -> dict:
        qa_agent = AGENT_FACTORIES["qa"](llm, tools=self._qa_tools())
        qa_prompt = (
            f"project_id={project_id}\n"
            f"User feedback: {user_message}"
        )
        
        print(f"[QA] Starting QA with prompt: {qa_prompt}")
        _raw_reply = await run_turn(qa_agent, session_id=f"{req_session_id}-qa", message=qa_prompt)
        print(f"[QA] Raw agent reply: {_raw_reply}")
        
        proj = get_or_create_project(project_id, req_session_id)
        reply = '{"message": "QA review completed."}'
        return self._build_response(
            proj=proj,
            reply=reply,
        )