# -*- coding: utf-8 -*-
"""شارپ تعدیل‌شده (Deflated Sharpe Ratio) — Bailey و López de Prado (۲۰۱۴).

چرا لازم است: وقتی ده‌ها فرضیه آزموده می‌شود، «بهترین» نتیجه حتی روی دادهٔ کاملاً تصادفی هم
شارپ بالایی نشان می‌دهد. DSR می‌پرسد: با در نظر گرفتن تعداد آزمون‌ها، طول داده، چولگی و
کشیدگی بازده‌ها، احتمال اینکه شارپ واقعی این روش بیشتر از صفر باشد چقدر است؟

PSR(SR*) = Z[ (SR − SR*) · √(T−1) / √(1 − skew·SR + ((kurt−1)/4)·SR²) ]
SR* (آستانهٔ مورد انتظار بیشینه در N آزمون مستقل) =
    √Var(SR) · [ (1−γ)·Z⁻¹(1 − 1/N) + γ·Z⁻¹(1 − 1/(N·e)) ]
γ = ثابت اویلر–ماسکرونی. همهٔ شارپ‌ها باید در یک بسامد (اینجا: روزانه) باشند.
فقط محاسبه — هیچ داده‌ای تغییر نمی‌کند.
"""
from __future__ import annotations

import math
from statistics import NormalDist

GAMMA = 0.5772156649015329
_N = NormalDist()


def moments(rets: list[float]) -> dict:
    """میانگین، انحراف معیار، چولگی و کشیدگی (کشیدگی خام، نه مازاد)."""
    n = len(rets)
    if n < 3:
        raise ValueError("دادهٔ کافی نیست")
    m = sum(rets) / n
    var = sum((x - m) ** 2 for x in rets) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        raise ValueError("انحراف معیار صفر")
    skew = sum(((x - m) / sd) ** 3 for x in rets) / n
    kurt = sum(((x - m) / sd) ** 4 for x in rets) / n
    return {"n": n, "mean": m, "sd": sd, "skew": skew, "kurt": kurt, "sharpe_per_period": m / sd}


def psr(sr: float, n: int, skew: float, kurt: float, sr_benchmark: float = 0.0) -> float:
    """احتمال اینکه شارپ واقعی از sr_benchmark بیشتر باشد (شارپ‌ها هم‌بسامد)."""
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return float("nan")
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sharpe(n_trials: int, sd_of_trial_sharpes: float) -> float:
    """آستانهٔ شارپ که صرفاً از «بهترین از میان N آزمون» انتظار می‌رود (فرضیهٔ صفر)."""
    if n_trials < 2 or sd_of_trial_sharpes <= 0:
        return 0.0
    a = _N.inv_cdf(1.0 - 1.0 / n_trials)
    b = _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return sd_of_trial_sharpes * ((1.0 - GAMMA) * a + GAMMA * b)


def deflated_sharpe(rets: list[float], n_trials: int, sd_of_trial_sharpes: float,
                    periods_per_year: int = 365) -> dict:
    """خروجی: شارپ خام و سالانه، آستانهٔ انتظار، و DSR (احتمال واقعی بودن لبه)."""
    mo = moments(rets)
    sr = mo["sharpe_per_period"]
    sr_star = expected_max_sharpe(n_trials, sd_of_trial_sharpes)
    return {
        "n_obs": mo["n"], "n_trials": n_trials,
        "sd_of_trial_sharpes_per_period": round(sd_of_trial_sharpes, 6),
        "sharpe_annual": round(sr * math.sqrt(periods_per_year), 3),
        "skew": round(mo["skew"], 3), "kurtosis": round(mo["kurt"], 3),
        "threshold_sharpe_annual": round(sr_star * math.sqrt(periods_per_year), 3),
        "psr_vs_zero": round(psr(sr, mo["n"], mo["skew"], mo["kurt"], 0.0), 4),
        "dsr": round(psr(sr, mo["n"], mo["skew"], mo["kurt"], sr_star), 4),
    }


def verdict(dsr_value: float, threshold: float = 0.95) -> str:
    """قاعدهٔ متعارف: DSR ≥ ۰٫۹۵ یعنی لبه پس از تصحیح چندآزمونی معنادار است."""
    if dsr_value != dsr_value:
        return "UNDEFINED"
    return "SIGNIFICANT_AFTER_MULTIPLE_TESTING" if dsr_value >= threshold else "NOT_SIGNIFICANT_AFTER_MULTIPLE_TESTING"
