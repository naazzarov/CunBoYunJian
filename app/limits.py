"""Bound request bodies before multipart parsing can spool them to disk."""
import json
import shutil
from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self,app,max_upload,directory=None,min_free=0):
        self.app=app;self.max_upload=max_upload;self.directory=directory;self.min_free=min_free;self.uploads=0

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH'):
            return await self.app(scope,receive,send)
        limit=self.max_upload+6*1024*1024 if scope['path']=='/api/jobs' else 2*1024*1024
        headers=dict(scope.get('headers',[]))
        try:length=int(headers.get(b'content-length',b'0'))
        except ValueError:length=0
        if length>limit:return await JSONResponse({'detail':'Request exceeds the upload limit.'},413)(scope,receive,send)
        upload=scope['path']=='/api/jobs'
        if upload:
            if self.uploads>=2:return await JSONResponse({'detail':'Two uploads are already in progress. Try again shortly.'},429)(scope,receive,send)
            if self.directory and shutil.disk_usage(self.directory()).free<self.min_free+max(length,limit):return await JSONResponse({'detail':'Not enough free storage. Delete exported sessions or ask the workspace owner.'},507)(scope,receive,send)
            self.uploads+=1
        total=0;exceeded=False;started=False
        async def bounded_receive():
            nonlocal total,exceeded
            message=await receive()
            total+=len(message.get('body',b''))
            if total>limit:
                exceeded=True
                # Disconnect prevents the multipart parser from retaining the rest of the upload.
                return {'type':'http.disconnect'}
            return message
        async def bounded_send(message):
            nonlocal started
            if exceeded:
                if not started:
                    started=True
                    body=json.dumps({'detail':'Request exceeds the upload limit.'}).encode()
                    await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
                    await send({'type':'http.response.body','body':body})
                return
            if message['type']=='http.response.start':started=True
            await send(message)
        try:await self.app(scope,bounded_receive,bounded_send)
        except Exception:
            if not exceeded:raise
            if not started:
                await JSONResponse({'detail':'Request exceeds the upload limit.'},413)(scope,receive,send)
        finally:
            if upload:self.uploads-=1
