import { AlertCircle } from 'lucide-react'

interface PlaceholderPageProps {
    title: string
    description: string
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
    return (
        <div className="h-full flex flex-col items-center justify-center text-center space-y-4 max-w-lg mx-auto">
            <div className="bg-gray-800 p-6 rounded-full">
                <AlertCircle size={48} className="text-gray-500" />
            </div>
            <h2 className="text-2xl font-bold">{title}</h2>
            <p className="text-gray-400">
                {description}
            </p>
            <div className="pt-6 grid grid-cols-2 gap-4 w-full">
                <div className="h-24 bg-gray-900 border border-gray-800 border-dashed rounded flex items-center justify-center text-xs text-gray-600">
                    Metric Panel Slot
                </div>
                <div className="h-24 bg-gray-900 border border-gray-800 border-dashed rounded flex items-center justify-center text-xs text-gray-600">
                    Feed Panel Slot
                </div>
            </div>
        </div>
    )
}
