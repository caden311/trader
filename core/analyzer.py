import re

import anthropic
import structlog

from config.sector_map import SECTOR_ETF_MAP
from config.settings import settings
from models.analysis import AnalysisResult
from models.post import Post

logger = structlog.get_logger()

SYSTEM_PROMPT = f"""You are a financial analyst AI. Your job is to analyze social media posts
from the President of the United States and determine their potential impact on financial markets.

You must evaluate each post and return a structured analysis. Be conservative in your assessments.
Only mark posts as relevant if they clearly relate to economic policy, trade, specific industries,
regulations, international relations affecting markets, or similar market-moving topics.

Posts about personal matters, birthdays, endorsements of non-market candidates, or general
political commentary without clear economic implications should be marked as NOT relevant.

You MUST respond with ONLY valid JSON matching this schema:
{{
  "is_relevant": boolean,
  "reasoning": "string",
  "sentiment": number (-1.0 to 1.0),
  "affected_sectors": ["string"],
  "affected_tickers": ["string"],
  "confidence": number (0.0 to 1.0),
  "direction": "buy" | "sell" | "hold",
  "urgency": "immediate" | "moderate" | "low"
}}

When assessing sentiment:
- Positive sentiment (towards 1.0): tax cuts, deregulation, pro-business policies, trade deals
- Negative sentiment (towards -1.0): tariffs, sanctions, trade wars, regulatory threats, geopolitical tension

Available sectors to map to: {', '.join(SECTOR_ETF_MAP.keys())}

Be specific about which sectors are affected. If the impact is broad/unclear, use "broad_market".
Only suggest "buy" or "sell" when you have reasonable confidence. Default to "hold" when uncertain."""


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM responses."""
    match = re.match(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text.strip(), re.DOTALL)
    return match.group(1).strip() if match else text.strip()


class PostAnalyzer:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def analyze(self, post: Post) -> AnalysisResult:
        """Analyze a post for market impact using Claude."""
        logger.info("analyzing_post", post_id=post.id, text_preview=post.text[:100])

        user_message = (
            f"Analyze this Truth Social post from President Trump for market impact.\n\n"
            f"Post (published {post.created_at.isoformat()}):\n"
            f'"{post.text}"'
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        result_text = response.content[0].text
        analysis = AnalysisResult.model_validate_json(_strip_code_fences(result_text))

        logger.info(
            "analysis_complete",
            post_id=post.id,
            is_relevant=analysis.is_relevant,
            sentiment=analysis.sentiment,
            confidence=analysis.confidence,
            direction=analysis.direction,
            tickers=analysis.affected_tickers,
        )

        return analysis

    def analyze_batch(self, posts: list[Post]) -> AnalysisResult:
        """Analyze multiple posts together when they arrive in rapid succession."""
        if len(posts) == 1:
            return self.analyze(posts[0])

        logger.info("analyzing_batch", count=len(posts))

        combined_text = "\n\n".join(
            f"Post {i + 1} ({p.created_at.isoformat()}):\n\"{p.text}\""
            for i, p in enumerate(posts)
        )

        user_message = (
            f"Analyze these {len(posts)} Truth Social posts from President Trump together. "
            f"They were posted in rapid succession. Provide a single combined market analysis.\n\n"
            f"{combined_text}"
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        result_text = response.content[0].text
        analysis = AnalysisResult.model_validate_json(_strip_code_fences(result_text))

        logger.info(
            "batch_analysis_complete",
            count=len(posts),
            is_relevant=analysis.is_relevant,
            direction=analysis.direction,
            confidence=analysis.confidence,
        )

        return analysis
