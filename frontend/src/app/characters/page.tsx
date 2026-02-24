import CharacterLibrary from '@/components/CharacterLibrary';
import RouteProtection from '@/components/RouteProtection';

export default function CharactersPage() {
  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <CharacterLibrary />
    </RouteProtection>
  );
}
