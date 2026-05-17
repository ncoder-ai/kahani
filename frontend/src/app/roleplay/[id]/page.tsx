'use client';

import { useParams } from 'next/navigation';
import RouteProtection from '@/components/RouteProtection';
import RoleplaySession from '@/components/roleplay/RoleplaySession';

export default function RoleplaySessionPage() {
  const params = useParams();
  const id = Number(params.id);

  return (
    <RouteProtection requireAuth={true} requireApproval={true}>
      <RoleplaySession key={id} roleplayId={id} />
    </RouteProtection>
  );
}
