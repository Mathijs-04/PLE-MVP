<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;

class ChatController extends Controller
{
    public function ask(Request $request)
    {
        $validated = $request->validate([
            'message' => 'required|string',
            'game' => 'required|in:aos,40k',
        ]);

        return response()->json([
            'received' => $validated,
        ]);
    }
}
