package com.payflow.app;

import android.os.Bundle;
import android.view.WindowManager;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(ChaveAparelhoPlugin.class);
        super.onCreate(savedInstanceState);
        // Sem print, gravação ou espelhamento de tela, e a miniatura em "apps recentes" sai
        // em branco: os trojans bancários do Brasil filmam a tela para roubar senha e saldo.
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE);
    }
}
