import type { NavigationItem } from "@/lib/navTypes";

export const navigationItems: NavigationItem[] = [
  { icon: "home", label: "Главная", description: "Дашборд и запуск проверок", to: "/dashboard" },
  { icon: "jobs", label: "Очередь", description: "Задачи и их статусы", to: "/jobs" },
  { icon: "scheduler", label: "Планировщик", description: "Расписание и email", to: "/scheduler" },
  { icon: "reports", label: "Отчёты", description: "Сводка и результаты", to: "/reports" },
  { icon: "protocols", label: "Протоколы", description: "Сканирование и OCR", to: "/protocols" },
  { icon: "arshin", label: "Аршин", description: "Токен и статус API", to: "/arshin" },
  { icon: "settings", label: "Настройки", description: "Параметры системы", to: "/settings" },
];
