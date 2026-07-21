from json import JSONDecodeError

import httpx
from rid_lib import RID
from rid_lib.ext import Bundle
from rid_lib.types import HTTP, HTTPS

from ..interfaces.deref_handler import DerefHandler


class HTTPDerefHandler(DerefHandler):
    """Simple dereferencer for HTTP(S) RIDs."""
    
    rid_types=(HTTP, HTTPS)
    
    def handle(self, rid: RID):
        """Sends a GET request to URL, returns a `Bundle` if the content
        is JSON, otherwise returns `None`.
        """
        
        resp = httpx.get(
            url=str(rid),
            follow_redirects=True
        )
        
        try:
            data = resp.json()
            return Bundle.generate(
                rid=rid,
                contents=data
            )
        except JSONDecodeError:
            return