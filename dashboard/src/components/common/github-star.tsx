import { useTheme } from '@/app/providers/theme-provider'
import { REPO_URL } from '@/constants/Project'
import GitHubButton from 'react-github-btn'

export const GithubStar = () => {
  const { theme } = useTheme()
  const gBtnColor = theme === 'dark' ? 'dark_dimmed' : theme
  // Hidden until the public DR-VPN repository URL is configured.
  if (!REPO_URL) return null
  return (
    <GitHubButton
      href={REPO_URL}
      data-color-scheme={`no-preference: ${gBtnColor}; light: ${gBtnColor}; dark: ${gBtnColor};`}
      data-size="large"
      data-show-count="true"
      aria-label="Star DR-VPN on GitHub"
    >
      Star
    </GitHubButton>
  )
}
