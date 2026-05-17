import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
  'Cache-Control': 'no-store',
} as const;

export async function GET() {
  return NextResponse.json(
    {
      status: 'healthy',
      app: 'Kahani',
      component: 'frontend',
    },
    { headers: HEADERS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: HEADERS });
}
