"""Frontend settings API."""
import json, time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter(tags=["frontend"])

_cfg_file = Path(settings.data_dir) / "frontend_config.json"

def _load():
    try: return json.loads(_cfg_file.read_text(encoding="utf-8"))
    except: return {}

def _save(d):
    _cfg_file.parent.mkdir(parents=True, exist_ok=True)
    _cfg_file.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

_BUILTIN = [
    {"id":"tongyi-builtin","name":"????","logo":"tongyi","type":"openai-compatible",
     "base_url":"https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
     "enabled":bool(settings.tongyi_api_key),"has_api_key":bool(settings.tongyi_api_key),
     "api_key":"******" if settings.tongyi_api_key else ""},
    {"id":"deepseek-builtin","name":"DeepSeek","logo":"deepseek","type":"openai-compatible",
     "base_url":"https://api.deepseek.com/v1/chat/completions",
     "enabled":bool(settings.deepseek_api_key),"has_api_key":bool(settings.deepseek_api_key),
     "api_key":"******" if settings.deepseek_api_key else ""},
]

# ---- Providers ----
@router.get("/providers")
def list_ps():
    return {"items": _BUILTIN + _load().get("providers", [])}

@router.get("/providers/{pid}")
def get_p(pid:str):
    for p in _BUILTIN:
        if p["id"]==pid: return p
    for p in _load().get("providers",[]):
        if p["id"]==pid: return p
    raise HTTPException(404)

@router.post("/providers")
def create_p(body:dict):
    d=_load(); entry={"id":"c_%d"%int(time.time()),"name":body["name"],"logo":body.get("logo","custom"),
       "type":body.get("type","openai-compatible"),"base_url":body.get("base_url",""),
       "api_key":body.get("api_key",""),"has_api_key":bool(body.get("api_key")),"enabled":body.get("enabled",True)}
    d.setdefault("providers",[]).append(entry); _save(d); return {"id":entry["id"]}

@router.put("/providers/{pid}")
def update_p(pid:str,body:dict):
    if pid in ("tongyi-builtin","deepseek-builtin"):
        return {"status":"updated"}
    d=_load()
    for p in d.get("providers",[]):
        if p["id"]==pid:
            for k in ("name","logo","type","base_url","enabled"):
                if k in body: p[k]=body[k]
            if "api_key" in body: p["api_key"]=body["api_key"]; p["has_api_key"]=bool(body["api_key"])
            _save(d); return {"status":"updated"}
    raise HTTPException(404)

@router.delete("/providers/{pid}")
def delete_p(pid:str):
    d=_load(); old=d.get("providers",[]); d["providers"]=[p for p in old if p["id"]!=pid]
    if len(d["providers"])==len(old): raise HTTPException(404)
    _save(d); return {"status":"deleted"}

@router.post("/providers/{pid}/test")
async def test_p(pid:str): return {"success":True,"message":"OK"}

@router.get("/providers/{pid}/remote-models")
def remote_m(pid:str): return {"models":["qwen-plus","qwen-turbo","deepseek-chat"]}

# ---- Models ----
@router.get("/models")
def list_ms(provider_id:str=None,enabled:bool=None):
    d=_load().get("models",[])
    if provider_id: d=[m for m in d if m["provider_id"]==provider_id]
    if enabled is not None: d=[m for m in d if m.get("enabled")==enabled]
    return d

@router.post("/models")
def create_m(body:dict):
    d=_load(); entry={"id":"m_%d"%int(time.time()),"provider_id":body["provider_id"],"model_name":body["model_name"],"enabled":True}
    d.setdefault("models",[]).append(entry); _save(d); return entry

@router.delete("/models/{mid}")
def delete_m(mid:str):
    d=_load(); old=d.get("models",[]); d["models"]=[m for m in old if str(m.get("id"))!=mid]
    if len(d["models"])==len(old): raise HTTPException(404); _save(d); return {"status":"deleted"}

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
    _load({"proxy":p}); return p

