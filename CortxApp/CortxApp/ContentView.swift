//
//  ContentView.swift
//  CortxApp
//
//  Created by Yaduraj Singh on 26/03/26.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: AppSessionViewModel

    var body: some View {
        Group {
            if session.isBootstrapping {
                ZStack {
                    AppBackgroundView()
                    VStack(spacing: 10) {
                        ProgressView()
                            .scaleEffect(1.15)
                        Text("Loading...")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            } else if session.isAuthenticated {
                DashboardView(session: session)
                    .transition(.opacity)
            } else {
                AuthView(session: session)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: session.isAuthenticated)
        .onAppear {
            session.bootstrapIfNeeded()
        }
    }
}
