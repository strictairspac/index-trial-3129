import logging,math
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from sqlalchemy.exc import IntegrityError
def _clean(o):
 if isinstance(o,float) and not math.isfinite(o):return str(o)
 if isinstance(o,dict):return {k:_clean(v) for k,v in o.items()}
 if isinstance(o,(list,tuple)):return [_clean(v) for v in o]
 return o
def install_errors(app):
 @app.exception_handler(RequestValidationError)
 async def invalid(request,exc):return JSONResponse({'detail':_clean(jsonable_encoder(exc.errors()))},status_code=422)
 @app.exception_handler(IntegrityError)
 async def conflict(request,exc):return JSONResponse({'detail':'名称已存在或关联数据不存在，请修改后重试'},status_code=409)
 @app.exception_handler(Exception)
 async def failure(request,exc):
  logging.exception('request failure')
  return JSONResponse({'detail':'服务暂时不可用，输入已保留，请稍后重试'},status_code=500)
