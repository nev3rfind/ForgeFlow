from typing import Dict, List, Optional
from pydantic import BaseModel

class ProviderModel(BaseModel):
    id: str
    name: str

class ProviderInfo(BaseModel):
    id: str
    display_name: str
    status: str
    supported_roles: List[str]
    models: List[ProviderModel]

class ProviderRegistry:
    def __init__(self):
        self.providers: Dict[str, ProviderInfo] = {}

    def register(self, info: ProviderInfo):
        self.providers[info.id] = info


    def load_custom(self):
        import os, json
        if os.path.exists("custom_providers.json"):
            try:
                with open("custom_providers.json", "r") as f:
                    data = json.load(f)
                    for item in data:
                        self.register(ProviderInfo(**item))
            except Exception as e:
                print(f"Failed to load custom providers: {e}")

    def save_custom(self, info: ProviderInfo):
        import os, json
        custom = []
        if os.path.exists("custom_providers.json"):
            try:
                with open("custom_providers.json", "r") as f:
                    custom = json.load(f)
            except:
                pass
        
        # Remove old if replacing
        custom = [c for c in custom if c.get("id") != info.id]
        custom.append(info.model_dump())
        
        with open("custom_providers.json", "w") as f:
            json.dump(custom, f, indent=2)
        
        self.register(info)

    def get_all(self) -> List[ProviderInfo]:
        return list(self.providers.values())

    def get(self, provider_id: str) -> Optional[ProviderInfo]:
        return self.providers.get(provider_id)

provider_registry = ProviderRegistry()

# Initialize with known providers
provider_registry.register(ProviderInfo(
    id="agy",
    display_name="Google Antigravity",
    status="Connected",
    supported_roles=["orchestrator", "investigator", "coder", "tester", "qa", "reviewer"],
    models=[
        ProviderModel(id="default", name="Default Model"),
        ProviderModel(id="flash", name="Flash (Fast)"),
        ProviderModel(id="pro", name="Pro (Complex)")
    ]
))

provider_registry.register(ProviderInfo(
    id="abacus",
    display_name="Abacus AI",
    status="Connected",
    supported_roles=["orchestrator", "investigator", "coder", "tester", "qa", "reviewer"],
    models=[
        ProviderModel(id="auto", name="Auto (Let Abacus Choose)"),
        ProviderModel(id="route-llm-code", name="RouteLLM (Code)"),
        ProviderModel(id="route-llm-code-low", name="RouteLLM (Code, Low)"),
        ProviderModel(id="route-llm", name="RouteLLM"),
        ProviderModel(id="claude-sonnet-5", name="Claude Sonnet 5"),
        ProviderModel(id="gpt-5.6-terra", name="GPT-5.6 Terra"),
        ProviderModel(id="gemini-3.8-flash", name="Gemini 3.8 Flash"),
        ProviderModel(id="grok-4.6", name="Grok 4.6"),
        ProviderModel(id="grok-4.5", name="Grok 4.5"),
        ProviderModel(id="claude-fable-5-1", name="Claude Fable 5.1"),
        ProviderModel(id="gpt-6-astra", name="GPT-6 Astra"),
        ProviderModel(id="gpt-5.6-sol", name="GPT-5.6 Sol"),
        ProviderModel(id="gemini-3.1-pro-preview", name="Gemini 3.1 Pro"),
        ProviderModel(id="claude-opus-5", name="Claude Opus 5"),
        ProviderModel(id="claude-opus-4-8", name="Claude Opus 4.8"),
        ProviderModel(id="gpt-5.5", name="GPT-5.5"),
        ProviderModel(id="gpt-5.6-luna", name="GPT-5.6 Luna"),
        ProviderModel(id="muse-spark-1.3", name="Muse Spark 1.3"),
        ProviderModel(id="muse-spark-1.2", name="Muse Spark 1.2"),
        ProviderModel(id="gpt-5.4-mini", name="GPT-5.4 Mini"),
        ProviderModel(id="grok-4.3", name="Grok 4.3"),
        ProviderModel(id="moonshotai/Kimi-K3", name="Kimi K3"),
        ProviderModel(id="moonshotai/Kimi-K2.7-Code", name="Kimi K2.7 Code"),
        ProviderModel(id="zai-org/GLM-5.3", name="GLM 5.3"),
        ProviderModel(id="zai-org/GLM-5.3-Flash", name="GLM 5.3 Flash"),
        ProviderModel(id="zai-org/GLM-5.2", name="GLM 5.2"),
        ProviderModel(id="deepseek-ai/DeepSeek-V4.1-Flash", name="Deepseek V4.1 Flash"),
        ProviderModel(id="deepseek-ai/DeepSeek-V4-Pro-0813", name="Deepseek V4 Pro"),
        ProviderModel(id="deepseek-ai/DeepSeek-V4-Flash-0731", name="Deepseek V4 Flash 0731"),
        ProviderModel(id="deepseek-ai/DeepSeek-V4-Flash-Vision-Exp", name="Deepseek V4 Flash Vision Exp"),
        ProviderModel(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5"),
        ProviderModel(id="gpt-5.4-nano", name="GPT-5.4 Nano"),
        ProviderModel(id="gemini-3.5-flash-lite", name="Gemini 3.5 Flash Lite"),
        ProviderModel(id="gemini-3.1-flash-lite", name="Gemini 3.1 Flash Lite"),
        ProviderModel(id="gemini-3-flash-preview", name="Gemini 3 Flash"),
        ProviderModel(id="claude-sonnet-4-6", name="Claude Sonnet 4.6"),
        ProviderModel(id="gpt-5.4", name="GPT-5.4"),
        ProviderModel(id="gemini-3.7-flash", name="Gemini 3.7 Flash"),
        ProviderModel(id="thinkingmachines/Inkling", name="Tinker Inkling"),
        ProviderModel(id="muse-spark-1.1", name="Muse Spark 1.1"),
        ProviderModel(id="mimo-v2-pro", name="MiMo V2 Pro"),
        ProviderModel(id="MiniMaxAI/MiniMax-M3", name="MiniMax M3"),
        ProviderModel(id="MiniMaxAI/MiniMax-M2.7", name="MiniMax M2.7"),
        ProviderModel(id="google/gemma-4-31b-it", name="Gemma 4 31B IT"),
        ProviderModel(id="zai-org/GLM-5.1", name="GLM 5.1"),
        ProviderModel(id="zai-org/GLM-5", name="GLM 5"),
        ProviderModel(id="zai-org/GLM-4.7", name="GLM 4.7"),
        ProviderModel(id="zai-org/GLM-4.6", name="GLM 4.6"),
        ProviderModel(id="moonshotai/Kimi-K2.6", name="Kimi K2.6"),
        ProviderModel(id="moonshotai/Kimi-K2-Instruct", name="Kimi K2 Turbo"),
        ProviderModel(id="Qwen/Qwen3.8-Flash-Next", name="Qwen3.8 Flash Next"),
        ProviderModel(id="Qwen/Qwen3.8-27B", name="Qwen3.8 27B"),
        ProviderModel(id="qwen3.8-max", name="Qwen3.8 Max"),
        ProviderModel(id="qwen3.7-max", name="Qwen3.7 Max"),
        ProviderModel(id="Qwen/Qwen3.6-27B", name="Qwen3.6 27B"),
        ProviderModel(id="Qwen/Qwen3-Coder-480B-A35B-Instruct", name="Qwen3 Coder"),
        ProviderModel(id="Qwen/Qwen3-32B", name="Qwen3 32B"),
        ProviderModel(id="abacusai/Smaug-Flash", name="Smaug Flash"),
        ProviderModel(id="gemini-3.6-flash", name="Gemini 3.6 Flash"),
        ProviderModel(id="gemini-3.5-flash", name="Gemini 3.5 Flash"),
        ProviderModel(id="gemini-3.1-flash-image", name="Nano Banana 2 (Gemini 3.1 Flash Image)"),
        ProviderModel(id="gemini-3-pro-image", name="Nano Banana (Gemini 3 Pro Image)"),
        ProviderModel(id="gemini-2.5-flash-image", name="Nano Banana (Gemini 2.5 Flash Image)"),
        ProviderModel(id="gemini-2.5-flash", name="Gemini 2.5 Flash"),
        ProviderModel(id="gemini-2.5-pro", name="Gemini 2.5 Pro"),
        ProviderModel(id="claude-fable-5", name="Claude Fable 5"),
        ProviderModel(id="claude-opus-4-7", name="Claude Opus 4.7"),
        ProviderModel(id="claude-opus-4-6", name="Claude Opus 4.6"),
        ProviderModel(id="claude-opus-4-5-20251101", name="Claude Opus 4.5"),
        ProviderModel(id="claude-sonnet-4-5-20250929", name="Claude Sonnet 4.5"),
        ProviderModel(id="openai/gpt-oss-120b", name="GPT-OSS 120B"),
        ProviderModel(id="gpt-5.3-codex", name="GPT-5.3 Codex"),
        ProviderModel(id="gpt-5.2", name="GPT-5.2"),
        ProviderModel(id="gpt-5.1", name="GPT-5.1"),
        ProviderModel(id="gpt-5-nano", name="GPT-5 Nano"),
        ProviderModel(id="gpt-5-mini", name="GPT-5 Mini"),
        ProviderModel(id="gpt-5", name="GPT-5"),
        ProviderModel(id="gpt-4.1-nano", name="GPT-4.1 Nano"),
        ProviderModel(id="gpt-4.1-mini", name="GPT-4.1 Mini"),
        ProviderModel(id="gpt-4.1", name="GPT-4.1"),
        ProviderModel(id="o3-mini", name="o3 Mini"),
        ProviderModel(id="o3", name="o3"),
        ProviderModel(id="o3-pro", name="o3 Pro"),
        ProviderModel(id="o4-mini", name="o4 Mini"),
        ProviderModel(id="gpt-realtime-whisper", name="GPT Realtime Whisper"),
        ProviderModel(id="gpt-transcribe", name="GPT Transcribe"),
        ProviderModel(id="gpt-4o-transcribe", name="GPT 4o Transcribe"),
        ProviderModel(id="gpt-4o-mini-transcribe", name="GPT 4o Mini Transcribe"),
        ProviderModel(id="gpt-4o-mini", name="GPT-4o Mini"),
        ProviderModel(id="gpt-4o", name="GPT-4o"),
        ProviderModel(id="gpt_image15", name="GPT Image 1.5"),
        ProviderModel(id="gpt_image15_edit", name="GPT Image 1.5 [Edit]"),
        ProviderModel(id="gpt_image2", name="GPT Image 2"),
        ProviderModel(id="gpt_image2_edit", name="GPT Image 2 [Edit]"),
        ProviderModel(id="gpt_image25", name="GPT Image 2.5"),
        ProviderModel(id="gpt_image25_edit", name="GPT Image 2.5 [Edit]"),
        ProviderModel(id="flux_kontext", name="FLUX.1 Kontext"),
        ProviderModel(id="flux_kontext_edit", name="FLUX.1 Kontext [Edit]"),
        ProviderModel(id="flux_pro", name="FLUX 1.1 [pro]"),
        ProviderModel(id="flux_pro_ultra", name="FLUX 1.1 [pro] Ultra"),
        ProviderModel(id="ideogram", name="Ideogram 3.0"),
        ProviderModel(id="ideogram_character", name="Ideogram Character"),
        ProviderModel(id="recraft", name="Recraft"),
        ProviderModel(id="recraft_svg", name="Recraft SVG"),
        ProviderModel(id="recraft_vectorize", name="Recraft Vectorize"),
        ProviderModel(id="dalle", name="DALL-E"),
        ProviderModel(id="magnific", name="Magnific Upscaler"),
        ProviderModel(id="flux_pro_canny", name="FLUX 1.1 [pro] Canny [Edit]"),
        ProviderModel(id="flux_pro_depth", name="FLUX 1.1 [pro] Depth [Edit]"),
        ProviderModel(id="gpt_image_edit", name="GPT Image [Edit]"),
        ProviderModel(id="midjourney", name="Midjourney"),
        ProviderModel(id="seedream", name="Seedream 4.5"),
        ProviderModel(id="seedream5_lite", name="Seedream 5 Lite"),
        ProviderModel(id="seedream5_pro", name="Seedream 5 Pro"),
        ProviderModel(id="dreamina", name="Dreamina"),
        ProviderModel(id="nano_banana", name="Nano Banana"),
        ProviderModel(id="nano_banana_pro", name="Nano Banana Pro"),
        ProviderModel(id="nano_banana2", name="Nano Banana 2"),
        ProviderModel(id="nano_banana25", name="Nano Banana 2.5"),
        ProviderModel(id="nano_banana_lite", name="Nano Banana Lite"),
        ProviderModel(id="qwen_image_edit", name="Qwen Image Edit"),
        ProviderModel(id="imagine_art", name="Imagineart 1.5"),
        ProviderModel(id="hunyuan_image", name="Hunyuan Image 3.0"),
        ProviderModel(id="flux2", name="FLUX.2"),
        ProviderModel(id="flux2_pro", name="FLUX.2 [Pro]"),
        ProviderModel(id="grok_imagine_image", name="Grok Imagine Image"),
        ProviderModel(id="grok_imagine_image2", name="Grok Imagine Image 2"),
        ProviderModel(id="grok_imagine_image_quality", name="Grok Imagine Quality"),
        ProviderModel(id="wan27", name="Wan 2.7"),
        ProviderModel(id="meta_muse_image", name="Meta Muse Image"),
        ProviderModel(id="gpt-audio-1.5", name="GPT Audio 1.5"),
        ProviderModel(id="gpt-audio-mini", name="GPT Audio Mini"),
        ProviderModel(id="gemini-2.5-flash-preview-tts", name="Gemini 2.5 Flash TTS"),
        ProviderModel(id="gemini-2.5-pro-preview-tts", name="Gemini 2.5 Pro TTS"),
        ProviderModel(id="hume", name="Hume"),
        ProviderModel(id="elevenlabs", name="ElevenLabs"),
        ProviderModel(id="openai_tts", name="OpenAI"),
        ProviderModel(id="minimax_tts", name="MiniMax Speech 2.8 HD"),
        ProviderModel(id="vibevoice", name="VibeVoice"),
        ProviderModel(id="seed_speech", name="Seed Speech"),
        ProviderModel(id="seed_audio", name="Seed Audio 1.0"),
        ProviderModel(id="runway", name="Runway"),
        ProviderModel(id="luma_labs", name="Luma Labs"),
        ProviderModel(id="kling_ai", name="Kling AI v1.6"),
        ProviderModel(id="kling_ai_v2", name="Kling AI v2"),
        ProviderModel(id="kling_ai_v21", name="Kling AI v2.1"),
        ProviderModel(id="minimax", name="Hailuo 2"),
        ProviderModel(id="hunyuan", name="Hunyuan Video"),
        ProviderModel(id="wan", name="Wan 2.2"),
        ProviderModel(id="wan25", name="Wan 2.5"),
        ProviderModel(id="topaz", name="Topaz Upscaler"),
        ProviderModel(id="seedance", name="Seedance"),
        ProviderModel(id="seedance_pro", name="Seedance Pro"),
        ProviderModel(id="kling_ai_v25", name="Kling AI v2.5"),
        ProviderModel(id="sora", name="Sora 2"),
        ProviderModel(id="veo31", name="Veo 3.1"),
        ProviderModel(id="veo31_lite", name="Veo 3.1 Lite"),
        ProviderModel(id="kling_ai_v26", name="Kling AI v2.6"),
        ProviderModel(id="kling_ai_v26_motion", name="Kling v2.6 Motion Control"),
        ProviderModel(id="kling_ai_v3", name="Kling AI v3"),
        ProviderModel(id="kling_ai_v3_motion", name="Kling v3 Motion Control"),
        ProviderModel(id="kling_ai_o1", name="Kling AI O1"),
        ProviderModel(id="kling_ai_o3", name="Kling AI O3"),
        ProviderModel(id="seedance15_pro", name="Seedance 1.5 Pro"),
        ProviderModel(id="seedance20", name="Seedance 2.0"),
        ProviderModel(id="seedance20_mini", name="Seedance 2.0 Mini"),
        ProviderModel(id="seedance25", name="Seedance 2.5"),
        ProviderModel(id="grok_imagine_video", name="Grok Imagine Video"),
        ProviderModel(id="grok_imagine_video15", name="Grok Imagine Video 1.5"),
        ProviderModel(id="gemini_omni_flash", name="Gemini Omni Flash"),
        ProviderModel(id="gemini_omni_flash11", name="Gemini Omni Flash 1.1"),
        ProviderModel(id="minimax_h3", name="MiniMax H3"),
        ProviderModel(id="wan27_video", name="Wan 2.7"),
        ProviderModel(id="wan30_video", name="Wan 3.0"),
        ProviderModel(id="flux3", name="FLUX 3")
    ]
))

provider_registry.load_custom()
