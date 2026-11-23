import { Button } from '../components/ui'

export default function NotFoundPage() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <p className="gradient-text font-display text-7xl font-extrabold">404</p>
      <h1 className="mt-4 text-2xl font-bold text-slate-900 dark:text-white">Page not found</h1>
      <p className="mt-2 text-slate-600 dark:text-slate-400">The page you are looking for does not exist or has expired.</p>
      <Button to="/" className="mt-8">Back to home</Button>
    </div>
  )
}
