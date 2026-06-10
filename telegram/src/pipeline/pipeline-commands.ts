/**
 * WaggleBot 파이프라인 전용 명령 처리.
 * /status, /posts, /approve, /reject, /crawl 지원.
 */
import { TelegramBotWrapper } from "../bot/telegram-bot.js";
import { buildKeyboard, button } from "../bot/keyboard.js";
import { logger } from "../utils/logger.js";
import {
  getPipelineStatus,
  getCollectedPosts,
  approvePost,
  rejectPost,
  triggerCrawl,
} from "./wagglebot-api.js";

const STATUS_LABELS: Record<string, string> = {
  COLLECTED: "📥 수집됨",
  EDITING: "✏️ 편집중",
  APPROVED: "✅ 승인됨",
  PROCESSING: "⚙️ 처리중",
  PREVIEW_RENDERED: "🎬 프리뷰 완료",
  RENDERED: "🎥 렌더 완료",
  UPLOADED: "🚀 업로드됨",
  FAILED: "❌ 실패",
  DECLINED: "🚫 거절됨",
};

export class PipelineCommands {
  constructor(private wrapper: TelegramBotWrapper) {}

  async sendStatus(chatId: number): Promise<void> {
    try {
      const status = await getPipelineStatus();
      const lines = ["📊 *파이프라인 현황*\n"];
      for (const [key, label] of Object.entries(STATUS_LABELS)) {
        const count = (status as Record<string, number>)[key] ?? 0;
        if (count > 0) lines.push(`${label}: *${count}*건`);
      }
      if (lines.length === 1) lines.push("처리 중인 게시글 없음");
      await this.wrapper.bot.sendMessage(chatId, lines.join("\n"), { parse_mode: "Markdown" });
    } catch (err) {
      logger.error("sendStatus error", { error: err });
      await this.wrapper.bot.sendMessage(chatId, "❌ 파이프라인 상태 조회 실패");
    }
  }

  async sendCollectedPosts(chatId: number): Promise<void> {
    try {
      const posts = await getCollectedPosts(10);
      if (posts.length === 0) {
        await this.wrapper.bot.sendMessage(chatId, "📭 승인 대기 게시글 없음");
        return;
      }
      for (const p of posts) {
        const score = p.engagementScore?.toFixed(1) ?? "-";
        const text =
          `[${p.siteCode.toUpperCase()}] #${p.id}\n` +
          `${p.title.slice(0, 60)}\n` +
          `점수: ${score}`;
        const kb = buildKeyboard([
          [
            button("✅ 승인", `approve:${p.id}`),
            button("❌ 거절", `reject:${p.id}`),
          ],
        ]);
        await this.wrapper.bot.sendMessage(chatId, text, { reply_markup: kb });
      }
    } catch (err) {
      logger.error("sendCollectedPosts error", { error: err });
      await this.wrapper.bot.sendMessage(chatId, "❌ 게시글 목록 조회 실패");
    }
  }

  async handleApprove(chatId: number, postId: number): Promise<void> {
    try {
      await approvePost(postId);
      await this.wrapper.bot.sendMessage(chatId, `✅ #${postId} 승인 완료`);
    } catch (err) {
      logger.error("handleApprove error", { postId, error: err });
      await this.wrapper.bot.sendMessage(chatId, `❌ #${postId} 승인 실패`);
    }
  }

  async handleReject(chatId: number, postId: number): Promise<void> {
    try {
      await rejectPost(postId);
      await this.wrapper.bot.sendMessage(chatId, `🚫 #${postId} 거절 완료`);
    } catch (err) {
      logger.error("handleReject error", { postId, error: err });
      await this.wrapper.bot.sendMessage(chatId, `❌ #${postId} 거절 실패`);
    }
  }

  async handleCrawl(chatId: number): Promise<void> {
    try {
      const result = await triggerCrawl();
      await this.wrapper.bot.sendMessage(chatId, `🕷️ 크롤링 시작 (jobId=${result.jobId})`);
    } catch (err) {
      logger.error("handleCrawl error", { error: err });
      await this.wrapper.bot.sendMessage(chatId, "❌ 크롤링 시작 실패");
    }
  }
}
