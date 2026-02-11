# src/core/exceptions.py
class LeadSkipped(Exception):
    """外部要因（CAPTCHA等）でテスト継続不能のためSKIPする"""
    pass
