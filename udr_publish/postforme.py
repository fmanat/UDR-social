"""Client minimal de l'API Post For Me (https://api.postforme.dev).

Points vérifiés dans le SDK officiel et le code source de Post For Me :
- authentification : en-tête `Authorization: Bearer <clé>` ;
- `isDraft: true` : post stocké chez Post For Me, jamais traité ni envoyé ;
- `PUT /v1/social-posts/{id}` recrée le post (même id) : sert à passer un
  brouillon en programmé ; refusé une fois le post traité ;
- `external_id` n'est pas unique côté API : l'idempotence est de notre côté.
"""

from __future__ import annotations

from dataclasses import dataclass


class PostForMeError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class ApiPost:
    id: str
    status: str
    scheduled_at: str | None
    external_id: str | None
    raw: dict


class PostForMeClient:
    def __init__(self, session, base_url: str, api_key: str | None, auth_via_proxy: bool = False,
                 timeout: float = 120):
        if not api_key and not auth_via_proxy:
            raise PostForMeError("clé Post For Me absente (POST_FOR_ME_API_KEY)")
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self.session.request(method, self.base_url + path, headers=self.headers,
                                        timeout=self.timeout, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code >= 400:
            raise PostForMeError(_error_message(response.status_code, body, response.text),
                                 response.status_code, response.text[:2000])
        return body if isinstance(body, dict) else {"data": body}

    @staticmethod
    def _post(body: dict) -> ApiPost:
        return ApiPost(body.get("id", ""), body.get("status", ""), body.get("scheduled_at"),
                       body.get("external_id"), body)

    def create_post(self, payload: dict) -> ApiPost:
        return self._post(self._request("POST", "/v1/social-posts", json=payload))

    def update_post(self, post_id: str, payload: dict) -> ApiPost:
        return self._post(self._request("PUT", f"/v1/social-posts/{post_id}", json=payload))

    def get_post(self, post_id: str) -> ApiPost:
        return self._post(self._request("GET", f"/v1/social-posts/{post_id}"))

    def find_by_external_id(self, external_id: str) -> list[ApiPost]:
        body = self._request("GET", "/v1/social-posts", params={"external_id": external_id, "limit": 10})
        return [self._post(p) for p in body.get("data") or [] if p.get("external_id") == external_id]

    def post_results(self, post_id: str) -> list[dict]:
        body = self._request("GET", "/v1/social-post-results", params={"post_id": post_id, "limit": 50})
        return list(body.get("data") or [])

    def list_accounts(self) -> list[dict]:
        """Comptes connectés, SANS les jetons (la réponse de l'API les contient)."""
        body = self._request("GET", "/v1/social-accounts", params={"limit": 100})
        keep = ("id", "platform", "username", "status", "external_id")
        return [{k: a.get(k) for k in keep} for a in body.get("data") or []]


def _error_message(status: int, body, text: str) -> str:
    if isinstance(body, dict):
        message = body.get("message") or body.get("error") or body
        if isinstance(message, list):
            message = " ; ".join(str(m) for m in message)
        return f"HTTP {status} : {message}"
    return f"HTTP {status} : {text[:500]}"
