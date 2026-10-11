/** Helpers for the Authentik single sign-on flow. */

export const OIDC_ERROR_MESSAGES: Record<string, string> = {
  disabled: "Единый вход сейчас недоступен.",
  discovery_failed: "Не удалось связаться с сервером входа.",
  missing_txn: "Сессия входа истекла. Попробуйте ещё раз.",
  bad_txn: "Сессия входа повреждена. Попробуйте ещё раз.",
  no_code: "Сервер входа не вернул код авторизации.",
  bad_state: "Проверка входа не прошла. Попробуйте ещё раз.",
  token_exchange_failed: "Не удалось завершить вход. Попробуйте ещё раз.",
  no_id_token: "Сервер входа не вернул токен.",
  bad_id_token: "Токен входа недействителен.",
  bad_nonce: "Токен входа не соответствует сессии.",
  no_email: "В учётной записи нет email.",
  no_access: "У этой учётной записи нет доступа к metroCheck.",
};

export function oidcErrorMessage(code: string | null | undefined): string | null {
  if (!code) {
    return null;
  }
  return OIDC_ERROR_MESSAGES[code] ?? "Не удалось выполнить вход через единый вход.";
}
