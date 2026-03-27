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
                        Text("Warming up your workspace...")
                            .font(.system(.footnote, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 22)
                    .padding(.vertical, 18)
                    .liquidCard()
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
