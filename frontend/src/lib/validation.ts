export function validateNewPassword(password: string, confirm: string): string | null {
	if (password.length < 8) return 'Password must be at least 8 characters.';
	if (password !== confirm) return 'Passwords do not match.';
	return null;
}
