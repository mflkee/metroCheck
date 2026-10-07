# metroChek — frontend

React + TypeScript + Vite + Tailwind CSS v4 + [shadcn/ui](https://ui.shadcn.com).

- **Тема:** shadcn `neutral`, только тёмная (dark-only), шрифт Geist, `--radius: 0.625rem`.
- **Стиль компонентов:** `radix-nova` preset (см. `components.json`).
- **Роутинг:** `react-router-dom` (`/` — дашборд, `/scheduler` — планировщик).
- **API:** тонкая обёртка в `src/lib/api.ts` поверх `/api` (JWT в `localStorage`).

## Разработка

```bash
npm install
npm run dev      # http://localhost:5173 (прокси /api не настроен — нужен backend)
npm run build    # tsc -b && vite build → dist/
npm run lint     # oxlint
```

## Сборка образа

Образ собирается мультистейджем из `frontend/Dockerfile` (context = корень репозитория):

```bash
docker build -f frontend/Dockerfile -t metrocheck-frontend:test .
```

## Добавление компонентов shadcn

```bash
npx shadcn@latest add <component>
```

> `components.json` использует alias `@/*` → `src/*`. Если CLI положит файлы в
> буквальный каталог `@/`, значит он не увидел `paths` в `tsconfig.json` — перенеси
> их в `src/` вручную.
