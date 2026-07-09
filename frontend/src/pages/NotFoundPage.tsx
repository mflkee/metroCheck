import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";

export function NotFoundPage() {
  return (
    <div className="space-y-5">
      <PageHeader title="Страница не найдена" description="Запрошенный раздел не существует" />
      <Link className="btn-primary" to="/dashboard">
        На главную
      </Link>
    </div>
  );
}
