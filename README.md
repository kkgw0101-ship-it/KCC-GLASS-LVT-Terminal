# KCC Glass LVT Intelligence Terminal

Streamlit Community Cloud 배포용 공유 버전입니다.

## 배포 파일

- `app_v6_share.py`
- `llm_analysis.py`
- `logo_white_t.png`
- `logo_navy_t.png`
- `requirements.txt`

## Streamlit Secrets

Streamlit Cloud의 **App settings > Secrets**에 아래 값을 입력합니다.

```toml
FRED_API_KEY = "본인_FRED_API_KEY"
ANTHROPIC_API_KEY = "본인_ANTHROPIC_API_KEY"
```

## 실행 파일

Streamlit Cloud에서 main file path는 아래로 지정합니다.

```text
app_v6_share.py
```
