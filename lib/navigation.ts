import {
  Bot,
  ClipboardCheck,
  Gauge,
  LayoutDashboard,
  Settings,
  Users,
  Shield,
} from "lucide-react";

export const navItems = [
  { key: "nav.dashboard", href: "/dashboard", icon: LayoutDashboard },
  { key: "nav.campaigns", href: "/campaigns", icon: Gauge },
  { key: "nav.contentStudio", href: "/content-studio", icon: Bot },
  { key: "nav.review", href: "/review", icon: ClipboardCheck },
  { key: "nav.members", href: "/members", icon: Users },
  { key: "nav.roles", href: "/roles", icon: Shield },
  { key: "nav.admin", href: "/admin/platform", icon: Settings },
  { key: "nav.system", href: "/system", icon: Settings },
] as const;
