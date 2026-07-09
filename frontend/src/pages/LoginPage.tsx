import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { loginUser } from "@/api/auth";
import { useAuthStore } from "@/store/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: loginUser,
    onSuccess: (data) => {
      setSession({ token: data.access_token, user: data.user });
      navigate("/dashboard", { replace: true });
    },
    onError: () => {
      setError("Неверное имя пользователя или пароль");
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    loginMutation.mutate({ username, password });
  }

  return (
    <form className="space-y-5" onSubmit={handleSubmit}>
      <div className="space-y-1">
        <label className="block text-sm font-semibold text-steel" htmlFor="username">
          Имя пользователя
        </label>
        <input
          autoComplete="username"
          className="form-input"
          id="username"
          placeholder="username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
      </div>

      <div className="space-y-1">
        <label className="block text-sm font-semibold text-steel" htmlFor="password">
          Пароль
        </label>
        <input
          autoComplete="current-password"
          className="form-input"
          id="password"
          placeholder="••••••••"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>

      {error ? (
        <div className="rounded-xl border border-[var(--danger)] bg-[color-mix(in_srgb,var(--danger)_12%,var(--tone-child-bg))] px-4 py-2 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : null}

      <button
        className="btn-primary w-full"
        disabled={loginMutation.isPending || !username || !password}
        type="submit"
      >
        {loginMutation.isPending ? "Вход..." : "Войти"}
      </button>
    </form>
  );
}
