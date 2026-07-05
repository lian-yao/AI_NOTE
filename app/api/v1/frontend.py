"""Frontend settings API."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.core.config import settings

router = APIRouter(tags=["frontend"])

_cfg_file = Path(settings.data_dir) / "frontend_config.json"

def _load():
    try: return json.loads(_cfg_file.read_text(encoding="utf-8"))
    except: return {}

def _save(d):
    _cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _cfg_file.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- Transcribers ----
_WS=["tiny","base","small","medium","large-v3"]

@router.get("/transcribers/config")
def get_tc():
    return {"transcriber_type":"fast-whisper","whisper_model_size":settings.whisper_model_size or "tiny",
        "available_types":[{"value":"fast-whisper","label":"fast-whisper"},{"value":"bcut","label":"??"}],
        "whisper_model_sizes":_WS,"mlx_whisper_available":False}

@router.put("/transcribers/config")
def update_tc(body:dict): return {"status":"updated"}

@router.get("/transcribers/models/status")
def get_ms():
    return {"whisper":[{"model_size":s,"downloaded":s==settings.whisper_model_size,"downloading":False} for s in _WS],"mlx_whisper":[],"mlx_available":False}

@router.post("/transcribers/models/download")
def dl_model(): return {"status":"started"}

@router.get("/transcribers/whisper-models")
def list_wm():
    c=_load().get("whisper_models",{}); return {"builtin":{s:s for s in _WS},"custom":c}

@router.post("/transcribers/whisper-models")
def add_wm(body:dict):
    d=_load(); d.setdefault("whisper_models",{})[body["name"]]=body["target"]; _save(d); return {"status":"created"}

@router.delete("/transcribers/whisper-models/{name}")
def del_wm(name:str):
    d=_load(); m=d.get("whisper_models",{})
    if name not in m: raise HTTPException(404)
    del m[name]; _save(d); return {"status":"deleted"}

# ---- Platform Cookies ----
@router.get("/platforms/{platform}/cookie")
def get_cookie(platform:str):
    c=_load().get("cookies",{}); return {"platform":platform,"cookie":c.get(platform,"")}

@router.put("/platforms/{platform}/cookie")
def set_cookie(platform:str,body:dict):
    d=_load(); d.setdefault("cookies",{})[platform]=body["cookie"]; _save(d); return {"platform":platform,"cookie":body["cookie"]}

# ---- Network Proxy ----
@router.get("/network/proxy")
def get_proxy():
    p=_load().get("proxy",{"enabled":False,"url":""}); p["effective"]=p["url"] if p["enabled"] else ""; return p

@router.put("/network/proxy")
def set_proxy(body:dict):
    p={"enabled":body.get("enabled",False),"url":body.get("url","")}; p["effective"]=p["url"] if p["enabled"] else ""
    d = _load(); d["proxy"] = p; _save(d); return p

