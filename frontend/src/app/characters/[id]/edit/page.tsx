'use client';

import { useParams } from 'next/navigation';
import CharacterForm from '@/components/CharacterForm';

export default function EditCharacterPage() {
  const params = useParams();
  const characterId = parseInt(params.id as string);

  return <CharacterForm characterId={characterId} mode="edit" />;
}