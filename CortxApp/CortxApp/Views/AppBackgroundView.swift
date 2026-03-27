import SwiftUI

struct AppBackgroundView: View {
    @State private var animate = false

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.95, green: 0.98, blue: 1.00),
                    Color(red: 0.89, green: 0.95, blue: 1.00),
                    Color(red: 0.88, green: 0.96, blue: 0.98)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            Circle()
                .fill(Color(red: 0.28, green: 0.62, blue: 0.98).opacity(0.24))
                .frame(width: 340, height: 340)
                .offset(x: animate ? -140 : -70, y: animate ? -300 : -200)
                .blur(radius: 14)

            Circle()
                .fill(Color(red: 0.22, green: 0.86, blue: 0.84).opacity(0.20))
                .frame(width: 280, height: 280)
                .offset(x: animate ? 165 : 90, y: animate ? 260 : 170)
                .blur(radius: 18)

            Circle()
                .fill(Color.white.opacity(0.35))
                .frame(width: 240, height: 240)
                .offset(x: animate ? 55 : 145, y: animate ? -140 : -70)
                .blur(radius: 24)
        }
        .animation(.easeInOut(duration: 8).repeatForever(autoreverses: true), value: animate)
        .onAppear {
            animate = true
        }
    }
}
