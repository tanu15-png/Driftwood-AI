import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from '@/components/ui/alert-dialog'
import type { Thread } from '@/lib/api'

export default function DeleteChatDialog({ thread, onClose, onConfirm }: {
  thread: Thread | null
  onClose: () => void
  onConfirm: (thread: Thread) => void
}) {
  return <AlertDialog open={thread !== null} onOpenChange={(open) => { if (!open) onClose() }}>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
        <AlertDialogDescription>“{thread?.title ?? 'New conversation'}” and its messages and citations will be permanently deleted.</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel>Cancel</AlertDialogCancel>
        <AlertDialogAction className="bg-destructive text-white hover:bg-destructive/90" onClick={() => { if (thread) onConfirm(thread) }}>Delete</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
}
