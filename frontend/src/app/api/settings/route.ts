import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:9876';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    
    const response = await fetch(`${BACKEND_URL}/api/settings/`, {
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
    console.error('Settings API error:', error);
    return NextResponse.json(
      { detail: 'Failed to fetch settings' },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/api/settings/`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader || '',
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(data, { status: response.status });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('Settings update API error:', error);
    return NextResponse.json(
      { detail: 'Failed to update settings' },
      { status: 500 }
    );
  }
}