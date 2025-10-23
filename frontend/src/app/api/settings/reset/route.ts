import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:9876';

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');

    const response = await fetch(`${BACKEND_URL}/api/settings/reset`, {
      method: 'POST',
      headers: {
        'Authorization': authHeader || '',
      },
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Settings reset API error:', error);
    return NextResponse.json(
      { detail: 'Failed to reset settings' },
      { status: 500 }
    );
  }
}