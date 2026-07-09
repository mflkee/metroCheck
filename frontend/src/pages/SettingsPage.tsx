import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";
import { PageHeader } from "@/components/layout/PageHeader";
import { useAuthStore } from "@/store/auth";

export function SettingsPage() {
  const user = useAuthStore((state) => state.user);

  return (
    <div className="space-y-5">
      <PageHeader title="Настройки" description="Параметры приложения и внешний вид" />

      <div className="card">
        <div className="card__header">Внешний вид</div>
        <div className="card__body">
          <ThemeSwitcher />
        </div>
      </div>

      <div className="card">
        <div className="card__header">Текущий пользователь</div>
        <div className="card__body space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-steel">Логин</span>
            <span className="font-medium text-ink">{user?.username ?? "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-steel">Роль</span>
            <span className="font-medium text-ink">{user?.role ?? "—"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
