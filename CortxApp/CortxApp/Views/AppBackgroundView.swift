import SwiftUI

struct AppBackgroundView: View {
    @State private var animate = false

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.96, green: 0.97, blue: 0.99),
                    Color(red: 0.89, green: 0.93, blue: 0.99)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(Color.blue.opacity(0.12))
                .frame(width: 280, height: 280)
                .offset(x: animate ? -120 : -80, y: animate ? -250 : -200)
                .blur(radius: 4)

            Circle()
                .fill(Color.cyan.opacity(0.14))
                .frame(width: 220, height: 220)
                .offset(x: animate ? 140 : 90, y: animate ? 260 : 210)
                .blur(radius: 8)
        }
        .animation(.easeInOut(duration: 5).repeatForever(autoreverses: true), value: animate)
        .onAppear {
            animate = true
        }
    }
}
