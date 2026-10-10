#!/usr/bin/env bash
set -euo pipefail
[ -d pack ] || { echo "Aucun pack dans ce commit : rien à envoyer."; exit 0; }
cd pack
if [ -z "${PUBLISH_SERVICE_TOKEN:-}" ]; then
  echo "::error::Secret PUBLISH_SERVICE_TOKEN absent dans GitHub (Settings > Secrets and variables > Actions)"; exit 2
fi
auth=(-H "Authorization: Bearer ${PUBLISH_SERVICE_TOKEN}")

if [ -f suivi.txt ]; then
  id=$(tr -d '[:space:]' < suivi.txt)
  echo "Suivi du pack $id"
  curl -sS --fail-with-body "${auth[@]}" "$SERVICE_URL/packs/$id/status" -o rep.json
  jq -r '.report_text' rep.json
  exit 0
fi

[ -f posts.json ] || { echo "::error::pack/posts.json manquant"; exit 2; }
args=(-F "posts_json=@posts.json;type=application/json")
v=$(jq -r '.media.vertical // empty' posts.json)
h=$(jq -r '.media.horizontal // empty' posts.json)
[ -n "$v" ] && [ -f "$v" ] && args+=(-F "video_vertical=@$v;type=video/mp4")
[ -n "$h" ] && [ -f "$h" ] && args+=(-F "video_horizontal=@$h;type=video/mp4")

echo "Envoi du pack $(jq -r .id posts.json) ($(jq -r .publish.mode posts.json), $(jq -r .publish.schedule posts.json))"
code=$(curl -sS "${auth[@]}" "${args[@]}" -o rep.json -w '%{http_code}' --max-time 900 "$SERVICE_URL/packs")
echo "HTTP $code"
jq -r '.report_text // .error // .' rep.json || cat rep.json
echo "RESULTAT_JSON_DEBUT"; cat rep.json; echo; echo "RESULTAT_JSON_FIN"
[ "$code" = "200" ] || exit 1
[ "$(jq -r '.refused // false' rep.json)" = "true" ] && exit 2
[ "$(jq -r '.ok // true' rep.json)" = "false" ] && exit 1
exit 0
