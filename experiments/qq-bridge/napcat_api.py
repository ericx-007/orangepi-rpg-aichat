"""Local management helper; does not expose credentials or message actions."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
class NapCat:
    def __init__(self):
        config=json.loads((ROOT/'qq-runtime/state/config/webui.json').read_text(encoding='utf-8'))
        assert config['host']=='127.0.0.1' and config['port']==6099
        self.base='http://127.0.0.1:6099/api'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.credential=None
        result=self.post('/auth/login',{'hash':hashlib.sha256((config['token']+'.napcat').encode()).hexdigest()})
        self.credential=result['Credential']
    def post(self,path,body=None):
        assert path.startswith('/') and '..' not in path
        headers={'Content-Type':'application/json'}
        if self.credential:headers['Authorization']='Bearer '+self.credential
        req=urllib.request.Request(self.base+path,data=json.dumps(body or {}).encode(),headers=headers)
        with self.opener.open(req,timeout=30) as response:result=json.load(response)
        if result.get('code')!=0:raise RuntimeError('NapCat management request failed: '+path)
        return result.get('data')

if __name__=='__main__':
    client=NapCat()
    status=client.post('/QQLogin/CheckLoginStatus')
    info=client.post('/QQLogin/GetQQLoginInfo')
    proof={'logged_in':status['isLogin'],'core_ready':status['coreReady'],'phase':status['loginPhase'],'bot_uin':str(info['uin']),'online':info.get('online')}
    (ROOT/'qq-runtime/state/login-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(proof))
