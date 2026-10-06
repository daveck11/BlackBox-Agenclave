import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Triage', end: true },
  { to: '/code-fix', label: 'Code-fix' },
  { to: '/workspace', label: 'Workspace', authOnly: true },
  { to: '/about', label: 'About' },
]

export default function Nav({ user }) {
  return (
    <nav className="nav">
      {LINKS.filter((l) => !l.authOnly || user).map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.end}
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
