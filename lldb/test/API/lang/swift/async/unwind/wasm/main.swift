func inner() async -> Int {
    return 42 // break here
}

func outer() async -> Int {
    return await inner()
}

@main struct Main {
    static func main() async {
        let result = await outer()
        print(result)
    }
}
