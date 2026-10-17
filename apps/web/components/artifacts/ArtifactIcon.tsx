import {
  AudioLines,
  BookOpenText,
  Code2,
  FileBarChart,
  FileQuestion,
  FileText,
  Film,
  Image as ImageIcon,
  Presentation,
  Sheet,
  type LucideProps,
} from "lucide-react";

const ICONS = {
  document: FileText,
  spreadsheet: Sheet,
  presentation: Presentation,
  image: ImageIcon,
  video: Film,
  audio: AudioLines,
  code: Code2,
  report: FileBarChart,
  research: BookOpenText,
  other: FileQuestion,
} as const;

export function ArtifactIcon({ type, ...props }: { type: string } & LucideProps) {
  const Icon = ICONS[type as keyof typeof ICONS] ?? FileQuestion;
  return <Icon {...props} />;
}
