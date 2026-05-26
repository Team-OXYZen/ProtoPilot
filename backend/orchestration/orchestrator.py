import json
import logging
import re
from typing import Any

from core.auth import get_oauth_token
from core.logging_utils import log_event
from core.runner import run_turn, run_turn_with_recovery
from core.sessions import session_service
from agents.registry import AGENT_FACTORIES
from orchestration.tools import (
    delete_angular_code_file,
    list_angular_code_files,
    load_artifacts_summary,
    load_angular_code_file,
    load_nontech_artifacts,
    load_spec,
    load_technical_artifacts,
    patch_angular_code_file,
    patch_nontech_artifact,
    patch_technical_artifact,
    rename_angular_code_file,
    run_angular_build,
    save_artifacts_summary,
    save_nontech_artifacts,
    save_technical_artifacts,
    set_project_stage,
    submit_spec,
    list_java_code_files,
    load_java_code_file,
    patch_java_code_file,
    delete_java_code_file,
    rename_java_code_file,
)
from orchestration.store import Stage, get_or_create_project, persist_project


class Orchestrator:

    # handle parsing of reply if it's a JSON string, otherwise return as is
    def _build_response(self, proj, reply: Any, artifacts_md: dict[str, str] | None = None, angular_code_files: dict[str, str] | None = None, raw_reply: str | None = None) -> dict[str, Any]:

        if reply and isinstance(reply, str):
            try:
                json_match = re.search(r'\{.*\}', reply, re.DOTALL)
                if json_match:
                    reply = json.loads(json_match.group())
            except json.JSONDecodeError:
                logging.warning(f"Failed to parse agent reply as JSON, returning raw string. Reply: {reply}")

        return {
            "stage": proj.stage,
            "reply": reply,
            "raw_reply": raw_reply,
            "spec": proj.spec,
            "nontech_artifacts_md": proj.nontech_artifacts_md,
            "technical_artifacts_md": proj.technical_artifacts_md,
            "artifacts_md": artifacts_md or proj.technical_artifacts_md or proj.nontech_artifacts_md,
            "angular_code_files": angular_code_files or proj.angular_code_files,
            "java_code_files": proj.java_code_files,
        }

    def _resume_context(self, proj, phase: str) -> str:
        spec = proj.spec or {}
        summary = {
            "project_id": proj.project_id,
            "phase": phase,
            "stage": proj.stage.value if hasattr(proj.stage, "value") else str(proj.stage),
            "project_name": spec.get("project_name"),
            "problem_statement": spec.get("problem_statement"),
            "goals": spec.get("goals", [])[:5],
            "target_users": spec.get("target_users", [])[:5],
            "nontech_artifact_files": list((proj.nontech_artifacts_md or {}).keys()),
            "technical_artifact_files": list((proj.technical_artifacts_md or {}).keys()),
            "has_artifacts_summary": bool(proj.artifacts_summary),
            "angular_code_files": list((proj.angular_code_files or {}).keys()),
            "java_code_files": list((proj.java_code_files or {}).keys()),
        }
        return (
            "Resume context from durable project state:\n"
            f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n"
            "Use the project tools to load exact content when needed. Existing generated files may be partial; "
            "continue from them instead of deleting and regenerating everything."
        )

    def _build_summary(self, build_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": build_result.get("ok"),
            "phase": build_result.get("phase"),
            "error": build_result.get("error"),
            "error_output": build_result.get("error_output"),
            "install_exit_code": (build_result.get("install") or {}).get("exit_code") if isinstance(build_result.get("install"), dict) else None,
            "build_exit_code": (build_result.get("build") or {}).get("exit_code") if isinstance(build_result.get("build"), dict) else None,
        }

    def _requirements_tools(self) -> list:
        return [submit_spec]

    def _artifacts_tools(self) -> list:
        return [load_spec, load_nontech_artifacts, save_nontech_artifacts, save_technical_artifacts, save_artifacts_summary]

    def _angular_codegen_tools(self) -> list:
        return [load_spec, load_artifacts_summary, list_angular_code_files, load_angular_code_file, patch_angular_code_file, delete_angular_code_file, rename_angular_code_file]

    def _code_review_tools(self) -> list:
        return [
            list_angular_code_files,
            load_angular_code_file,
            patch_angular_code_file,
            delete_angular_code_file,
            rename_angular_code_file,
            run_angular_build,
        ]

    def _qa_tools(self) -> list:
        return [
            load_spec,
            load_nontech_artifacts, load_technical_artifacts,
            patch_nontech_artifact, patch_technical_artifact,
            list_angular_code_files, load_angular_code_file,
            patch_angular_code_file, delete_angular_code_file, rename_angular_code_file,
            run_angular_build,
        ]

    async def _handle_wait_approval(self, proj, normalized: str) -> dict[str, Any]:
        if normalized == "approve":
            log_event("STAGE", "approval_received", {"project_id": proj.project_id, "from": proj.stage.value, "to": Stage.TECH_ARTIFACTS.value})
            set_project_stage(proj.project_id, Stage.TECH_ARTIFACTS)
            proj.stage=Stage.TECH_ARTIFACTS
            return {}

        if normalized == "change":
            log_event("STAGE", "revision_requested", {"project_id": proj.project_id, "from": proj.stage.value, "to": Stage.REQ.value})
            set_project_stage(proj.project_id, Stage.REQ)
            proj.stage=Stage.REQ
            return self._build_response(
                proj=proj,
                reply={"message": "You have entered revision mode. Please describe the changes needed."},
                artifacts_md=proj.nontech_artifacts_md,
            )

        return self._build_response(
            proj=proj,
            reply={"message": "Please reply with either 'approve' or 'change'."},
            artifacts_md=proj.nontech_artifacts_md,
        )

    async def _run_requirements(self, token, proj, req_session_id: str, user_message: str) -> dict[str, Any]:
        req_agent = AGENT_FACTORIES["requirements"](token, tools=self._requirements_tools())

        phase = "requirements_revision" if proj.nontech_artifacts_md else "requirements_gathering"

        req_prompt = (
            f"project_id={proj.project_id}\n"
            f"phase={phase}\n"
            "Continue requirements gathering for this project.\n"
            f"User message:\n{user_message}"
        )

        log_event("AGENT", "requirements_start", {"project_id": proj.project_id, "phase": phase, "session_id": req_session_id})
        reply = await run_turn(req_agent, req_session_id, message=req_prompt)
        log_event("AGENT", "requirements_done", {"project_id": proj.project_id, "stage": proj.stage.value, "reply": reply}, status="ok")

        if proj.stage == Stage.ARTIFACTS_NON_TECH and proj.spec:
            return await self._run_artifacts_non_tech(token, proj, req_session_id)

        return self._build_response(
            proj=proj,
            reply=reply,
            raw_reply=reply,
        )

    async def handle(self,project_id: str,req_session_id: str,user_message: str,user_id: str,project_title: str | None = None,project_description: str | None = None,) -> dict:
        proj = get_or_create_project(project_id=project_id,req_session_id=req_session_id,user_id=user_id,project_title=project_title,project_description=project_description,)
        normalized = user_message.strip().lower()
        log_event(
            "ORCH",
            "route",
            {
                "project_id": project_id,
                "session_id": req_session_id,
                "stage": proj.stage.value,
                "message": user_message,
            },
        )

        if proj.stage == Stage.WAIT_APPROVAL:
            approval_result = await self._handle_wait_approval(proj, normalized)
            if approval_result:
                return approval_result

        token = await get_oauth_token()

        if proj.stage == Stage.REQ:
            return await self._run_requirements(token, proj, req_session_id, user_message)
        if proj.stage == Stage.ARTIFACTS_NON_TECH:
            return await self._run_artifacts_non_tech(token, proj, req_session_id)
        if proj.stage == Stage.TECH_ARTIFACTS:
            return await self._run_artifacts_technical(token, proj, req_session_id)
        if proj.stage == Stage.CODEGEN:
            return await self._run_angular_codegen(token, proj, req_session_id)
        if proj.stage == Stage.QA:
            if normalized == "finalize":
                log_event("STAGE", "finalize_requested", {"project_id": proj.project_id, "from": proj.stage.value, "to": Stage.FINALIZE.value})
                set_project_stage(proj.project_id, Stage.FINALIZE)
                return await self._run_java_codegen(token, proj, req_session_id)
            return await self._run_qa(token, proj, req_session_id, user_message)
        if proj.stage == Stage.FINALIZE:
            return await self._run_java_codegen(token, proj, req_session_id)

        return self._build_response(
            proj=proj,
            reply={"message": "Project complete."},
        )

    async def _run_artifacts_non_tech(self, token, proj, req_session_id: str) -> dict:
        art_agent = AGENT_FACTORIES["artifacts"](token, tools=self._artifacts_tools(), phase="non_tech")

        art_prompt = (
            f"project_id={proj.project_id}\n"
            "phase=non_tech\n"
            "Generate PM-facing non-technical artifacts now.\n"
            "Save full content via save_nontech_artifacts(project_id, artifacts_dict) as a dictionary with filename keys and markdown content values, "
        )
        log_event("AGENT", "artifacts_nontech_start", {"project_id": proj.project_id, "session_id": f"{req_session_id}-nontech"})
        _raw_reply = await run_turn(art_agent, session_id=f"{req_session_id}-nontech", message=art_prompt)
        log_event("AGENT", "artifacts_nontech_done", {"project_id": proj.project_id, "stage": proj.stage.value, "reply": _raw_reply}, status="ok")

        if proj.stage != Stage.WAIT_APPROVAL:
            log_event("ERROR", "artifacts_nontech_failed", {"project_id": proj.project_id, "reply": _raw_reply}, status="fail")
            set_project_stage(proj.project_id, Stage.REQ)
            persist_project(proj.project_id)
            raise RuntimeError(f"Non-technical artifacts generation failed: {_raw_reply}")

        reply = {
            "message": _raw_reply,
            "raw_reply": _raw_reply,
        }

        return self._build_response(
            proj=proj,
            reply=reply,
            artifacts_md=proj.nontech_artifacts_md,
            raw_reply=_raw_reply,
        )

    async def _run_artifacts_technical(self, token, proj, req_session_id: str) -> dict:
        art_agent = AGENT_FACTORIES["artifacts"](token, tools=self._artifacts_tools(), phase="technical")

        art_prompt = (
            f"project_id={proj.project_id}\n"
            "phase=technical\n"
            "Generate technical artifacts now. "
            "Use load_spec(project_id) first, then save_technical_artifacts with a dictionary (filename keys, markdown content values) at the end."
        )

        log_event("AGENT", "artifacts_technical_start", {"project_id": proj.project_id, "session_id": f"{req_session_id}-tech"})
        _raw_reply = await run_turn(
            art_agent,
            session_id=f"{req_session_id}-tech",
            message=art_prompt,
        )
        log_event("AGENT", "artifacts_technical_done", {"project_id": proj.project_id, "artifact_files": list((proj.technical_artifacts_md or {}).keys()), "reply": _raw_reply}, status="ok")

        if not proj.technical_artifacts_md:
            log_event("ERROR", "artifacts_technical_failed", {"project_id": proj.project_id, "reply": _raw_reply}, status="fail")
            raise RuntimeError(f"Technical artifacts generation failed: {_raw_reply}")

        reply = {
            "message": _raw_reply,
            "raw_reply": _raw_reply,
        }

        return self._build_response(
            proj=proj,
            reply=reply,
            artifacts_md=proj.technical_artifacts_md,
            raw_reply=_raw_reply,
        )

    async def _run_angular_codegen(self, token, proj, req_session_id: str) -> dict:
        try:
            code_agent = AGENT_FACTORIES["code_generation"](token, tools=self._angular_codegen_tools())
            code_prompt = (
                f"project_id={proj.project_id}\n"
                "Generate a POC-level Angular frontend code now.\n"
                "Use tools to get requirements and artifacts, "
                "generate modular Angular components and services with mocked API calls, "
            )
            log_event("AGENT", "angular_codegen_start", {"project_id": proj.project_id, "session_id": f"{req_session_id}-codegen"})
            _raw_reply = await run_turn_with_recovery(
                code_agent,
                session_id=f"{req_session_id}-codegen",
                message=code_prompt,
                resume_context=self._resume_context(proj, "angular_codegen"),
                use_compaction=True,
                max_retries=1,
            )
            log_event("AGENT", "angular_codegen_done", {"project_id": proj.project_id, "files": list((proj.angular_code_files or {}).keys()), "reply": _raw_reply}, status="ok")

            if proj.angular_code_files:
                codegen_build_ok, codegen_verify_reply = await self._verify_angular_codegen_build(code_agent, proj, req_session_id)
                if not codegen_build_ok:
                    return self._build_response(
                        proj=proj,
                        reply={
                            "message": "Angular code was generated, but the build still fails after repair attempts.",
                            "codegen_verification": codegen_verify_reply,
                        },
                        angular_code_files=proj.angular_code_files,
                        raw_reply=f"{_raw_reply}\n\n[CODEGEN_BUILD_VERIFICATION]\n{codegen_verify_reply}",
                    )

                review_reply = await self._run_code_review(token, proj, req_session_id)
                return self._build_response(
                    proj=proj,
                    reply={"message": "Angular code generated, build-verified, and reviewed.", "codegen_verification": codegen_verify_reply, "review": review_reply},
                    angular_code_files=proj.angular_code_files,
                    raw_reply=f"{_raw_reply}\n\n[CODEGEN_BUILD_VERIFICATION]\n{codegen_verify_reply}\n\n[CODE_REVIEW]\n{review_reply}",
                )
            else:
                raise RuntimeError(f"Code generation failed: {_raw_reply}")
        except Exception as e:
            error_message = f"Code generation failed with error: {str(e)}"
            log_event("ERROR", "angular_codegen_failed", {"project_id": proj.project_id, "error": error_message}, status="fail")
            return self._build_response(proj=proj, reply={"message": error_message})

    async def _verify_angular_codegen_build(self, code_agent, proj, req_session_id: str) -> tuple[bool, str]:
        verification_messages: list[str] = []
        build_result = run_angular_build(proj.project_id)

        for attempt in range(1, 4):
            if build_result.get("ok"):
                verified_message = "Angular build verified by orchestrator after code generation."
                log_event("AGENT", "angular_codegen_build_verified", {"project_id": proj.project_id}, status="ok")
                verification_messages.append(verified_message)
                return True, "\n\n".join(verification_messages)

            log_event(
                "AGENT",
                "angular_codegen_repair_attempt",
                {"project_id": proj.project_id, "attempt": attempt, "build": self._build_summary(build_result)},
                status="retry",
            )
            repair_prompt = (
                f"project_id={proj.project_id}\n"
                f"codegen_build_repair_attempt={attempt}/3\n"
                "The backend orchestrator ran npm install and npm run build for the Angular project you generated, and it failed. "
                "Inspect the generated Angular files needed to fix the error, patch the smallest safe set of files, and do not claim success. "
                "The orchestrator will run the build again after your patch. Continue from existing saved files; do not regenerate the whole app unless unavoidable.\n\n"
                "Latest build result:\n"
                f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
            )
            repair_reply = await run_turn_with_recovery(
                code_agent,
                session_id=f"{req_session_id}-codegen-build-repair-{attempt}",
                message=repair_prompt,
                resume_context=self._resume_context(proj, f"angular_codegen_build_repair_{attempt}"),
                use_compaction=True,
                max_retries=1,
            )
            verification_messages.append(f"Codegen build repair attempt {attempt}: {repair_reply}")
            build_result = run_angular_build(proj.project_id)

        failure_message = (
            "Angular build still fails after 3 orchestrator-verified codegen repair attempts.\n"
            f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
        )
        log_event("ERROR", "angular_codegen_build_unresolved", {"project_id": proj.project_id, "build": self._build_summary(build_result)}, status="fail")
        verification_messages.append(failure_message)
        return False, "\n\n".join(verification_messages)

    async def _run_code_review(self, token, proj, req_session_id: str) -> str:
        review_messages: list[str] = []

        try:
            review_agent = AGENT_FACTORIES["code_review"](token, tools=self._code_review_tools())

            log_event("AGENT", "code_review_start", {"project_id": proj.project_id, "session_id": f"{req_session_id}-code-review"})
            build_result = run_angular_build(proj.project_id)

            for attempt in range(1, 4):
                if build_result.get("ok"):
                    break

                log_event(
                    "AGENT",
                    "code_review_repair_attempt",
                    {"project_id": proj.project_id, "attempt": attempt, "build": self._build_summary(build_result)},
                    status="retry",
                )
                repair_prompt = (
                    f"project_id={proj.project_id}\n"
                    f"repair_attempt={attempt}/3\n"
                    "The backend orchestrator ran the Angular build and it failed. "
                    "Inspect the generated Angular files needed to fix the error, patch the smallest safe set of files, "
                    "and do not claim success. The orchestrator will run the build again after your patch.\n\n"
                    "Latest build result:\n"
                    f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
                )
                repair_reply = await run_turn_with_recovery(
                    review_agent,
                    session_id=f"{req_session_id}-code-review-repair-{attempt}",
                    message=repair_prompt,
                    resume_context=self._resume_context(proj, f"code_review_repair_{attempt}"),
                    use_compaction=True,
                    max_retries=1,
                )
                review_messages.append(f"Repair attempt {attempt}: {repair_reply}")
                build_result = run_angular_build(proj.project_id)

            if not build_result.get("ok"):
                failure_message = (
                    "Angular build still fails after 3 orchestrator-verified repair attempts.\n"
                    f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
                )
                log_event("ERROR", "code_review_build_unresolved", {"project_id": proj.project_id, "build": self._build_summary(build_result)}, status="fail")
                review_messages.append(failure_message)
                return "\n\n".join(review_messages)

            ux_prompt = (
                f"project_id={proj.project_id}\n"
                "The backend orchestrator has verified that npm install and npm run build pass. "
                "Now perform the UX/functionality audit from your instructions. Check for one-page dumping, missing navigation, "
                "bare styling, missing icons/charts where useful, unclickable entity rows/cards, and buttons without real handlers. "
                "Patch any obvious UX completeness issues. If you patch anything, do not claim final build success; the orchestrator will verify again."
            )
            ux_reply = await run_turn_with_recovery(
                review_agent,
                session_id=f"{req_session_id}-code-review-ux",
                message=ux_prompt,
                resume_context=self._resume_context(proj, "code_review_ux"),
                use_compaction=True,
                max_retries=1,
            )
            review_messages.append(f"UX audit: {ux_reply}")

            final_build_result = run_angular_build(proj.project_id)
            for attempt in range(1, 4):
                if final_build_result.get("ok"):
                    break

                log_event(
                    "AGENT",
                    "code_review_post_ux_repair_attempt",
                    {"project_id": proj.project_id, "attempt": attempt, "build": self._build_summary(final_build_result)},
                    status="retry",
                )
                repair_prompt = (
                    f"project_id={proj.project_id}\n"
                    f"post_ux_repair_attempt={attempt}/3\n"
                    "The UX audit introduced or left a build error. Fix the build error only, preserving the improved UI where possible. "
                    "The orchestrator will verify the build again after your patch.\n\n"
                    "Latest build result:\n"
                    f"{json.dumps(self._build_summary(final_build_result), ensure_ascii=False, indent=2)}"
                )
                repair_reply = await run_turn_with_recovery(
                    review_agent,
                    session_id=f"{req_session_id}-code-review-post-ux-repair-{attempt}",
                    message=repair_prompt,
                    resume_context=self._resume_context(proj, f"code_review_post_ux_repair_{attempt}"),
                    use_compaction=True,
                    max_retries=1,
                )
                review_messages.append(f"Post-UX repair attempt {attempt}: {repair_reply}")
                final_build_result = run_angular_build(proj.project_id)

            if final_build_result.get("ok"):
                verified_message = "Angular build verified by orchestrator after code review."
                log_event("AGENT", "code_review_done", {"project_id": proj.project_id, "reply": verified_message}, status="ok")
                review_messages.append(verified_message)
            else:
                failure_message = (
                    "Angular build failed after UX audit and 3 orchestrator-verified repair attempts.\n"
                    f"{json.dumps(self._build_summary(final_build_result), ensure_ascii=False, indent=2)}"
                )
                log_event("ERROR", "code_review_final_build_failed", {"project_id": proj.project_id, "build": self._build_summary(final_build_result)}, status="fail")
                review_messages.append(failure_message)

            return "\n\n".join(review_messages)
        except Exception as e:
            error_message = f"Code review failed with error: {str(e)}"
            log_event("ERROR", "code_review_failed", {"project_id": proj.project_id, "error": error_message}, status="fail")
            return error_message
        finally:
            log_event("STAGE", "code_review_complete", {"project_id": proj.project_id, "to": Stage.QA.value})
            set_project_stage(proj.project_id, Stage.QA)
            proj.stage = Stage.QA
            persist_project(proj.project_id)

    def _java_codegen_tools(self) -> list:
        return [
            load_spec, load_artifacts_summary,
            list_angular_code_files, load_angular_code_file, patch_angular_code_file,
            list_java_code_files, load_java_code_file, patch_java_code_file,
            delete_java_code_file, rename_java_code_file,
        ]

    async def _run_java_codegen(self, token, proj, req_session_id: str) -> dict:
        from agents.code_generation_agent.instructions import JAVA_CODEGEN_INSTRUCTIONS
        try:
            code_agent = AGENT_FACTORIES["code_generation"](token, tools=self._java_codegen_tools(), instructions=JAVA_CODEGEN_INSTRUCTIONS)
            code_prompt = (
                f"project_id={proj.project_id}\n"
                "Generate a Java Spring Boot backend and update Angular services to use real API calls.\n"
                "Follow the instructions step by step: analyse Angular services first, then generate Java files one at a time, then update Angular services."
            )
            log_event("AGENT", "java_codegen_start", {"project_id": proj.project_id, "session_id": f"{req_session_id}-javacodegen"})
            _raw_reply = await run_turn_with_recovery(
                code_agent,
                session_id=f"{req_session_id}-javacodegen",
                message=code_prompt,
                resume_context=self._resume_context(proj, "java_codegen"),
                use_compaction=True,
                max_retries=1,
            )
            log_event("AGENT", "java_codegen_done", {"project_id": proj.project_id, "files": list((proj.java_code_files or {}).keys()), "reply": _raw_reply}, status="ok")

            if proj.java_code_files:
                return self._build_response(
                    proj=proj,
                    reply={"message": "Java Spring Boot code generated successfully."},
                    raw_reply=_raw_reply,
                )
            else:
                return self._build_response(
                    proj=proj,
                    reply={"message": "Java code generation failed. Please try again."},
                    raw_reply=_raw_reply,
                )
        except Exception as e:
            error_message = f"Java code generation failed with error: {str(e)}"
            log_event("ERROR", "java_codegen_failed", {"project_id": proj.project_id, "error": error_message}, status="fail")
            return self._build_response(proj=proj, reply={"message": error_message})

    async def _run_qa(self, llm, proj, req_session_id: str, user_message: str) -> dict:
        qa_agent = AGENT_FACTORIES["qa"](llm, tools=self._qa_tools())

        qa_prompt = (
            f"project_id={proj.project_id}\n"
            f"User feedback: {user_message}"
        )

        qa_session_id = f"{req_session_id}-qa"
        log_event("AGENT", "qa_start", {"project_id": proj.project_id, "session_id": qa_session_id, "feedback": user_message})
        _raw_reply = await run_turn_with_recovery(
            qa_agent,
            session_id=qa_session_id,
            message=qa_prompt,
            resume_context=self._resume_context(proj, "qa"),
            use_compaction=True,
            max_retries=1,
        )
        log_event("AGENT", "qa_done", {"project_id": proj.project_id, "reply": _raw_reply}, status="ok")

        qa_build_ok, qa_verification_reply = await self._verify_qa_build(qa_agent, proj, req_session_id)
        reply = {
            "message": f"{_raw_reply}",
            "build_verification": qa_verification_reply,
            "build_ok": qa_build_ok,
        }
        return self._build_response(
            proj=proj,
            reply=reply,
            raw_reply=f"{_raw_reply}\n\n[QA_BUILD_VERIFICATION]\n{qa_verification_reply}",
        )

    async def _verify_qa_build(self, qa_agent, proj, req_session_id: str) -> tuple[bool, str]:
        verification_messages: list[str] = []
        build_result = run_angular_build(proj.project_id)

        for attempt in range(1, 4):
            if build_result.get("ok"):
                verified_message = "Angular build verified by orchestrator after QA changes."
                log_event("AGENT", "qa_build_verified", {"project_id": proj.project_id}, status="ok")
                verification_messages.append(verified_message)
                return True, "\n\n".join(verification_messages)

            log_event(
                "AGENT",
                "qa_build_repair_attempt",
                {"project_id": proj.project_id, "attempt": attempt, "build": self._build_summary(build_result)},
                status="retry",
            )
            repair_prompt = (
                f"project_id={proj.project_id}\n"
                f"qa_build_repair_attempt={attempt}/3\n"
                "The QA changes left the Angular project failing npm install or npm run build. "
                "Inspect the generated Angular files needed to fix the error, patch the smallest safe set of files, "
                "and preserve the user's requested QA change. Do not claim success; the orchestrator will run the build again after your patch.\n\n"
                "Latest build result:\n"
                f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
            )
            repair_reply = await run_turn_with_recovery(
                qa_agent,
                session_id=f"{req_session_id}-qa-build-repair-{attempt}",
                message=repair_prompt,
                resume_context=self._resume_context(proj, f"qa_build_repair_{attempt}"),
                use_compaction=True,
                max_retries=1,
            )
            verification_messages.append(f"QA build repair attempt {attempt}: {repair_reply}")
            build_result = run_angular_build(proj.project_id)

        failure_message = (
            "Angular build still fails after QA changes and 3 orchestrator-verified repair attempts.\n"
            f"{json.dumps(self._build_summary(build_result), ensure_ascii=False, indent=2)}"
        )
        log_event("ERROR", "qa_build_unresolved", {"project_id": proj.project_id, "build": self._build_summary(build_result)}, status="fail")
        verification_messages.append(failure_message)
        return False, "\n\n".join(verification_messages)
