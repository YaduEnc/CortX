//
//  CortxAppApp.swift
//  CortxApp
//
//  Created by Yaduraj Singh on 26/03/26.
//

import SwiftUI

@main
struct CortxAppApp: App {
    @StateObject private var session = AppSessionViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(session)
        }
    }
}
