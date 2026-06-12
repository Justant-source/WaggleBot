"""
Monitoring and Alerting System

시스템 헬스 모니터링 및 알림 전송
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum
from typing import Optional

import psutil
import requests

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

from sqlalchemy import text

from config import settings
from db.session import SessionLocal

log = logging.getLogger(__name__)


class AlertLevel(Enum):
    """알림 레벨"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertManager:
    """시스템 헬스 체크 및 알림 관리자"""

    def __init__(self):
        self.smtp_configured = all([
            settings.EMAIL_ALERTS_ENABLED,
            settings.SMTP_USER,
            settings.SMTP_PASSWORD,
            settings.ALERT_EMAIL_TO
        ])
        self.slack_configured = (
            settings.SLACK_ALERTS_ENABLED and
            settings.SLACK_WEBHOOK_URL
        )

        if self.smtp_configured:
            log.info("Email alerts enabled: %s", settings.ALERT_EMAIL_TO)
        if self.slack_configured:
            log.info("Slack alerts enabled")

    def send_alert(self, level: AlertLevel, message: str, details: Optional[str] = None):
        """
        알림 전송

        Args:
            level: 알림 레벨 (INFO/WARNING/CRITICAL)
            message: 알림 메시지
            details: 상세 정보 (선택사항)
        """
        full_message = f"{message}\n\n{details}" if details else message

        # 로그 기록
        log_level = self._get_log_level(level)
        log.log(log_level, message)

        # CRITICAL 레벨만 외부 알림 전송
        if level == AlertLevel.CRITICAL:
            if self.smtp_configured:
                try:
                    self.send_email(f"[CRITICAL] {message}", full_message)
                except Exception:
                    log.exception("Failed to send email alert")

            if self.slack_configured:
                try:
                    self.send_slack(f":rotating_light: *[CRITICAL]* {message}", details)
                except Exception:
                    log.exception("Failed to send Slack alert")

        # WARNING은 로그만
        elif level == AlertLevel.WARNING:
            if details:
                log.debug("Warning details: %s", details)

    def send_email(self, subject: str, body: str):
        """
        이메일 알림 전송

        Args:
            subject: 이메일 제목
            body: 이메일 본문
        """
        if not self.smtp_configured:
            log.warning("Email not configured, skipping")
            return

        msg = MIMEMultipart()
        msg['From'] = settings.SMTP_USER
        msg['To'] = ", ".join(settings.ALERT_EMAIL_TO)
        msg['Subject'] = f"[WaggleBot] {subject}"

        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        log.info("Email sent to %s", settings.ALERT_EMAIL_TO)

    def send_slack(self, message: str, details: Optional[str] = None):
        """
        슬랙 알림 전송

        Args:
            message: 슬랙 메시지
            details: 상세 정보 (선택사항)
        """
        if not self.slack_configured:
            log.warning("Slack not configured, skipping")
            return

        payload = {
            "text": message,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
        }

        if details:
            payload["blocks"].append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{details}```"
                }
            })

        response = requests.post(
            settings.SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        log.info("Slack notification sent")

    def check_health(self) -> dict:
        """
        시스템 헬스 체크

        Returns:
            헬스 상태 딕셔너리 및 알림 전송
        """
        health_status = {
            'cpu_percent': None,
            'memory_percent': None,
            'disk_percent': None,
            'gpu_temp': None,
            'gpu_memory_percent': None,
            'db_connected': False,
            'alerts': []
        }

        # CPU 사용률
        try:
            health_status['cpu_percent'] = psutil.cpu_percent(interval=1)
        except Exception:
            log.exception("Failed to get CPU usage")

        # 메모리 사용률
        try:
            mem = psutil.virtual_memory()
            health_status['memory_percent'] = mem.percent

            if mem.percent >= settings.MEMORY_USAGE_CRITICAL:
                msg = f"메모리 사용률 CRITICAL: {mem.percent:.1f}%"
                self.send_alert(AlertLevel.CRITICAL, msg)
                health_status['alerts'].append(msg)
            elif mem.percent >= settings.MEMORY_USAGE_WARNING:
                msg = f"메모리 사용률 경고: {mem.percent:.1f}%"
                self.send_alert(AlertLevel.WARNING, msg)
                health_status['alerts'].append(msg)
        except Exception:
            log.exception("Failed to get memory usage")

        # 디스크 사용률
        try:
            disk = psutil.disk_usage('/')
            health_status['disk_percent'] = disk.percent

            if disk.percent >= settings.DISK_USAGE_CRITICAL:
                msg = f"디스크 사용률 CRITICAL: {disk.percent:.1f}%"
                details = f"Free: {disk.free / (1024**3):.1f}GB / Total: {disk.total / (1024**3):.1f}GB"
                self.send_alert(AlertLevel.CRITICAL, msg, details)
                health_status['alerts'].append(msg)
            elif disk.percent >= settings.DISK_USAGE_WARNING:
                msg = f"디스크 사용률 경고: {disk.percent:.1f}%"
                self.send_alert(AlertLevel.WARNING, msg)
                health_status['alerts'].append(msg)
        except Exception:
            log.exception("Failed to get disk usage")

        # GPU 상태
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    health_status['gpu_temp'] = gpu.temperature
                    health_status['gpu_memory_percent'] = (
                        gpu.memoryUsed / gpu.memoryTotal * 100 if gpu.memoryTotal > 0 else 0
                    )

                    # GPU 온도 체크
                    if gpu.temperature >= settings.GPU_TEMP_CRITICAL:
                        msg = f"GPU 온도 CRITICAL: {gpu.temperature}°C"
                        self.send_alert(AlertLevel.CRITICAL, msg)
                        health_status['alerts'].append(msg)
                    elif gpu.temperature >= settings.GPU_TEMP_WARNING:
                        msg = f"GPU 온도 경고: {gpu.temperature}°C"
                        self.send_alert(AlertLevel.WARNING, msg)
                        health_status['alerts'].append(msg)

                    # VRAM 사용률 체크 (파이프라인 유휴 중 누수 감지)
                    vram_pct = health_status['gpu_memory_percent'] or 0
                    vram_used_gb = gpu.memoryUsed / 1024 if gpu.memoryTotal > 0 else 0
                    if vram_pct >= settings.GPU_VRAM_CRITICAL:
                        msg = (
                            f"VRAM 사용률 CRITICAL: {vram_pct:.1f}% "
                            f"({vram_used_gb:.1f}GB / {gpu.memoryTotal / 1024:.0f}GB)"
                        )
                        self.send_alert(AlertLevel.CRITICAL, msg)
                        health_status['alerts'].append(msg)
                    elif vram_pct >= settings.GPU_VRAM_WARNING:
                        msg = (
                            f"VRAM 사용률 경고: {vram_pct:.1f}% "
                            f"({vram_used_gb:.1f}GB / {gpu.memoryTotal / 1024:.0f}GB) — 누수 의심"
                        )
                        self.send_alert(AlertLevel.WARNING, msg)
                        health_status['alerts'].append(msg)
            except Exception:
                log.exception("Failed to get GPU status")

        # DB 연결 체크
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                health_status['db_connected'] = True
        except Exception:
            log.exception("DB connection check failed")
            msg = "DB 연결 실패"
            self.send_alert(AlertLevel.CRITICAL, msg)
            health_status['alerts'].append(msg)

        # 헬스 상태 요약
        if not health_status['alerts']:
            log.info(
                "Health check OK - CPU: %.1f%%, MEM: %.1f%%, DISK: %.1f%%",
                health_status['cpu_percent'] or 0,
                health_status['memory_percent'] or 0,
                health_status['disk_percent'] or 0
            )
        else:
            log.warning("Health check completed with %d alerts", len(health_status['alerts']))

        return health_status

    def get_gpu_temp(self) -> Optional[float]:
        """
        GPU 온도 조회

        Returns:
            GPU 온도 (섭씨) 또는 None
        """
        if not GPU_AVAILABLE:
            return None

        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                return gpus[0].temperature
        except Exception:
            log.exception("Failed to get GPU temperature")

        return None

    def get_disk_usage(self) -> Optional[float]:
        """
        디스크 사용률 조회

        Returns:
            디스크 사용률 (%) 또는 None
        """
        try:
            return psutil.disk_usage('/').percent
        except Exception:
            log.exception("Failed to get disk usage")
            return None

    def check_db_connection(self) -> bool:
        """
        DB 연결 상태 체크

        Returns:
            연결 성공 여부
        """
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            return True
        except Exception:
            log.exception("DB connection failed")
            return False

    def _get_log_level(self, alert_level: AlertLevel) -> int:
        """
        AlertLevel을 logging level로 변환

        Args:
            alert_level: AlertLevel Enum

        Returns:
            logging level (INFO/WARNING/CRITICAL)
        """
        mapping = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(alert_level, logging.INFO)


# 싱글톤 인스턴스
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """AlertManager 싱글톤 인스턴스 반환"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
