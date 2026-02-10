interface Props {
  content: string
}

export default function DesignPreview({ content }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold text-gray-700">Design Preview</h3>
      <pre className="whitespace-pre-wrap text-sm text-gray-600">{content}</pre>
    </div>
  )
}
