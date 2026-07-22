func leaf() async -> Int {
    return 99
}

func caller() async -> Int {
    let a = 1
    let b = await leaf()   // step-over here should reach the next line, not enter leaf()
    return a + b           // desired landing
}

@main struct Main {
    static func main() async {
        let result = await caller()
        print(result)
    }
}
