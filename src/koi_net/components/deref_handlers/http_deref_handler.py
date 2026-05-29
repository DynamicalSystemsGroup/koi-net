from json import JSONDecodeError

import httpx
from rid_lib import RID
from rid_lib.ext import Bundle
from rid_lib.types import HTTP, HTTPS

from ..interfaces.deref_handler import DerefHandler


class HTTPDerefHandler(DerefHandler):
    rid_types=(HTTP, HTTPS)
    
    def handle(self, rid: RID):
        resp = httpx.get(str(rid))
        
        try:
            data = resp.json()
            return Bundle.generate(
                rid=rid,
                contents=data
            )
        except JSONDecodeError:
            return